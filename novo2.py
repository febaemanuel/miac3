from waitress import serve
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    send_from_directory,
    send_file,
    flash,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, inspect, JSON
from sqlalchemy.ext.mutable import MutableList
from dotenv import load_dotenv
import fitz
import json
import logging
import os
import re
import requests
import time
import traceback
import unicodedata
from datetime import datetime
from io import BytesIO
from werkzeug.utils import secure_filename

import qrcode
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    Image,
)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or os.urandom(24)

db_host = os.getenv("DB_HOST")
db_port = os.getenv("DB_PORT")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_name = os.getenv("DB_NAME")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
CHATGPT_API_KEY = os.getenv("CHATGPT_API_KEY", "")

# Configuração do SQLAlchemy
app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

UPLOAD_FOLDER2 = os.path.join("static", "uploads2")
os.makedirs(UPLOAD_FOLDER2, exist_ok=True)


users = {
    "usuario": {"senha": "senha123", "nivel_acesso": "padrao"},
    "admin": {"senha": "Qualidade@admin!", "nivel_acesso": "elevado"},
}


class Documento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(400))
    caminho = db.Column(db.String(200))
    data_publicacao = db.Column(db.String(50))
    data_elaboracao = db.Column(db.String(50))
    vencimento = db.Column(db.String(50), nullable=True)
    numero_sei = db.Column(db.String(50), nullable=True)
    elaboradores = db.Column(db.String(200), nullable=True)
    organograma = db.Column(db.String(100), nullable=True)
    tipo_documento = db.Column(db.String(100), nullable=True)
    # Novo campo: HUWC ou MEAC
    abrangencia = db.Column(db.String(50), nullable=True)
    # Novo campo: True (Atualizado) ou False (Desatualizado)
    atualizado = db.Column(db.Boolean, nullable=True)


class Documento2(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(400))  # Nome do arquivo PDF
    organograma = db.Column(db.String(100))  # Escolha do Organograma
    tipo_documento = db.Column(db.String(100))  # Escolha do Tipo de Documento
    caminho = db.Column(db.String(200))  # Caminho do arquivo PDF atual
    pdf_antigo = db.Column(db.String(200), nullable=True)  # Versão anterior imediata
    data_publicacao = db.Column(db.String(50))  # Data de publicação
    abrangencia = db.Column(db.String(50), nullable=True)  # HUWC ou MEAC
    atualizado = db.Column(
        db.Boolean, nullable=True
    )  # True (Atualizado) ou False (Desatualizado)
    data_elaboracao = db.Column(db.String(50), nullable=True)  # Data de Elaboração
    vencimento = db.Column(db.String(50), nullable=True)  # Data de Validade
    numero_sei = db.Column(db.String(50), nullable=True)  # Número SEI
    elaboradores = db.Column(db.String(1000), nullable=True)  # Elaboradores
    marcador = db.Column(db.String(100), nullable=True)  # Marcador
    nome_completo = db.Column(db.String(200), nullable=True)  # Adicione esta linha

    # Novos campos para versionamento avançado
    versao_atual = db.Column(db.Integer, default=1)  # Número da versão atual
    historico_versoes = db.Column(MutableList.as_mutable(JSON), default=list)
    data_atualizacao = db.Column(db.DateTime)  # Data da última atualização

    def __repr__(self):
        return f"<Documento2 {self.nome} (v{self.versao_atual})>"

    @property
    def versao_efetiva(self):
        return self.versao_atual if self.versao_atual is not None else 1

    @property
    def historico_efetivo(self):
        return self.historico_versoes if self.historico_versoes is not None else []


class Organograma(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True)


# Modelo para Tipo de Documento


class TipoDocumento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True)


# Função para criar o banco de dados e as tabelas


def criar_banco_de_dados():
    with app.app_context():
        # Verifica se o banco de dados já existe
        inspector = inspect(db.engine)
        if not inspector.has_table("documento") or not inspector.has_table(
            "documento2"
        ):
            # Cria todas as tabelas definidas nos modelos
            db.create_all()
            logger.info("Banco de dados e tabelas criados com sucesso!")
        else:
            logger.info("Banco de dados já existe.")


# Executa a função para criar o banco de dados
criar_banco_de_dados()

# Função de login


def login_user(username, password):
    if username in users and users[username]["senha"] == password:
        session["username"] = username
        session["nivel_acesso"] = users[username]["nivel_acesso"]
        return True
    return False


DATE_FORMATS = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"]


def parse_data(data_str):
    """Retorna datetime a partir de string em qualquer formato suportado."""
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(data_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Formato de data inválido: {data_str}")

def calcular_status(doc):
    """Retorna dict com status, detalhes, cor e vencimento formatado para um documento."""
    try:
        if not doc.vencimento:
            return {
                "status": "Sem data",
                "detalhes": "Sem data de vencimento",
                "cor": "gray",
                "vencimento": "N/A",
            }

        try:
            data_vencimento = parse_data(doc.vencimento)
        except ValueError:
            return {
                "status": "Inválido",
                "detalhes": "Formato desconhecido",
                "cor": "darkorange",
                "vencimento": doc.vencimento,
            }

        hoje = datetime.now()

        if data_vencimento >= hoje:
            dias_restantes = (data_vencimento - hoje).days
            return {
                "status": "Atualizado",
                "detalhes": f"Vence em {dias_restantes} dias",
                "cor": "green",
                "vencimento": data_vencimento.strftime("%d/%m/%Y"),
            }
        else:
            dias_vencido = (hoje - data_vencimento).days
            if dias_vencido < 30:
                tempo = f"Há {dias_vencido} dias"
            elif dias_vencido < 365:
                meses = dias_vencido // 30
                tempo = f"Há {meses} meses"
            else:
                anos = dias_vencido // 365
                resto_meses = (dias_vencido % 365) // 30
                tempo = f"Há {anos} anos e {resto_meses} meses"
            return {
                "status": "Vencido",
                "detalhes": tempo,
                "cor": "red",
                "vencimento": data_vencimento.strftime("%d/%m/%Y"),
            }
    except Exception:
        return {
            "status": "Inválido",
            "detalhes": "Data inválida",
            "cor": "darkorange",
            "vencimento": doc.vencimento if doc.vencimento else "N/A",
        }


@app.route("/miac/gerar_relatorio/<abrangencia>/<organograma>")
def gerar_relatorio(abrangencia, organograma):
    try:
        # Consulta os documentos no banco de dados
        documentos = Documento2.query.filter_by(
            organograma=organograma, abrangencia=abrangencia
        ).all()

        if not documentos:
            return "Nenhum documento encontrado para os critérios especificados", 404

        # Ordenação: primeiro por tipo de documento (A-Z), depois vencidos por último dentro do tipo
        documentos_ordenados = sorted(
            documentos,
            key=lambda doc: (
                (
                    doc.tipo_documento.lower() if doc.tipo_documento else ""
                ),  # Ordem alfabética por tipo
                not doc.atualizado,  # Atualizados primeiro (False < True)
                "Vencido" in calcular_status(doc)["status"],  # Vencidos por último
            ),
        )

        # Contagem total, atualizados e desatualizados
        total = len(documentos_ordenados)
        atualizados = sum(
            1
            for doc in documentos_ordenados
            if calcular_status(doc)["status"] == "Atualizado"
        )
        desatualizados = total - atualizados

        # Contagem por tipo de documento
        contagem_por_tipo = {}
        for doc in documentos_ordenados:
            tipo = doc.tipo_documento if doc.tipo_documento else "Sem Tipo"
            if tipo not in contagem_por_tipo:
                contagem_por_tipo[tipo] = {
                    "total": 0,
                    "atualizados": 0,
                    "desatualizados": 0,
                }
            contagem_por_tipo[tipo]["total"] += 1
            if calcular_status(doc)["status"] == "Atualizado":
                contagem_por_tipo[tipo]["atualizados"] += 1
            else:
                contagem_por_tipo[tipo]["desatualizados"] += 1

        # Buffer para armazenar o PDF
        buffer = BytesIO()

        # Configurações do PDF
        pdf_doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=1.5 * cm,
            rightMargin=1.5 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        # Estilos de texto
        styles = getSampleStyleSheet()

        # Estilo para o título principal
        style_title = ParagraphStyle(
            "Title",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=16,
            textColor=HexColor("#2c3e50"),
            leading=20,
            alignment=TA_CENTER,
            spaceAfter=12,
        )

        # Estilo para cabeçalhos
        style_header = ParagraphStyle(
            "Header",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=HexColor("#ffffff"),
            leading=12,
            alignment=TA_CENTER,
            backColor=HexColor("#2c3e50"),
        )

        # Estilo para rodapé
        style_footer = ParagraphStyle(
            "Footer",
            parent=styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=9,
            textColor=HexColor("#7f8c8d"),
            alignment=TA_CENTER,
            spaceBefore=10,
        )

        # Estilo normal
        style_normal = ParagraphStyle(
            "Normal",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
        )

        # Estilo para texto vencido
        style_vencido = ParagraphStyle(
            "Vencido",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=colors.red,
            leading=12,
        )

        # Estilo para texto atualizado
        style_atualizado = ParagraphStyle(
            "Atualizado",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            textColor=colors.green,
            leading=12,
        )

        # Estilo para subtítulos
        style_subtitle = ParagraphStyle(
            "Subtitle",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            textColor=HexColor("#3498db"),
            leading=14,
            spaceBefore=10,
            spaceAfter=6,
        )

        # Conteúdo do PDF
        content = []

        # Logo/Cabeçalho
        logo_path = os.path.join("static", "logo.png")
        if os.path.exists(logo_path):
            logo = Image(logo_path, width=120, height=60)
            content.append(logo)
            content.append(Spacer(1, 12))

        # Título do relatório
        content.append(
            Paragraph(
                f"<b>RELATÓRIO DE DOCUMENTOS - {organograma} ({abrangencia})</b>",
                style_title,
            )
        )

        # Data de geração
        content.append(
            Paragraph(
                f"<b>Data de geração:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
                style_normal,
            )
        )
        content.append(Spacer(1, 12))

        # ========== SEÇÃO 1: DETALHAMENTO POR TIPO DE DOCUMENTO ==========
        content.append(
            Paragraph("<b>DETALHAMENTO POR TIPO DE DOCUMENTO</b>", style_subtitle)
        )

        # Tabela de documentos (sem coluna de Tipo Documento)
        table_data = [["Nome do Documento", "Status/Vencimento", "Publicação", "Link"]]

        tipo_atual = None
        for i, documento in enumerate(documentos_ordenados, start=1):
            status_info = calcular_status(documento)

            # Adiciona cabeçalho de seção quando o tipo muda
            if documento.tipo_documento != tipo_atual:
                tipo_atual = documento.tipo_documento
                table_data.append(
                    [Paragraph(f"<b>{tipo_atual}</b>", style_header), "", "", ""]
                )

            # Formata o status e vencimento em uma única célula
            status_text = f"<b>{status_info['status']}</b><br/>"
            if status_info["status"] in ["Atualizado", "Vencido"]:
                status_text += (
                    f"{status_info['detalhes']}<br/>({status_info['vencimento']})"
                )
            else:
                status_text += status_info["detalhes"]

            # URL para visualização do documento
            base_url = request.url_root
            documento_url = f"https://hg.huwc.ufc.br/miac/documento2/{documento.id}"
            link_documento = f'<a href="{documento_url}" color="blue">Abrir</a>'
                       

            # Escolhe o estilo com base no status
            text_style = (
                style_vencido
                if status_info["status"] == "Vencido"
                else (
                    style_atualizado
                    if status_info["status"] == "Atualizado"
                    else style_normal
                )
            )

            # Adiciona linha na tabela
            table_data.append(
                [
                    Paragraph(documento.nome, text_style),
                    Paragraph(status_text, text_style),
                    Paragraph(
                        (
                            documento.data_publicacao.split()[0]
                            if documento.data_publicacao
                            else "N/A"
                        ),
                        text_style,
                    ),
                    Paragraph(link_documento, text_style),
                ]
            )

        # Cria a tabela com os estilos
        table = Table(table_data, colWidths=[10 * cm, 4 * cm, 2.5 * cm, 2.5 * cm])

        # Estilo da tabela
        table_style = TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8f9fa")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )

        # Adiciona spans para os cabeçalhos de seção
        for i, row in enumerate(table_data):
            if len(row) > 1 and row[1] == "":  # Linha de cabeçalho de seção
                table_style.add("SPAN", (0, i), (-1, i))
                table_style.add(
                    "BACKGROUND", (0, i), (-1, i), colors.HexColor("#495057")
                )
                table_style.add("TEXTCOLOR", (0, i), (-1, i), colors.white)

        table.setStyle(table_style)

        content.append(table)
        content.append(Spacer(1, 16))

        # ========== SEÇÃO 2: ALERTAS ==========
        # Seção de Documentos Vencidos/Próximos do Vencimento
        docs_vencidos = [
            doc
            for doc in documentos_ordenados
            if calcular_status(doc)["status"] == "Vencido"
        ]
        docs_proximo_vencer = [
            doc
            for doc in documentos_ordenados
            if calcular_status(doc)["status"] == "Atualizado"
            and doc.vencimento
            and (parse_data(doc.vencimento) - datetime.now()).days
            <= 30
        ]

        # Ordenar documentos próximos a vencer por data de vencimento (mais próximos primeiro)
        docs_proximo_vencer.sort(
            key=lambda doc: (
                parse_data(doc.vencimento) - datetime.now()
            ).days
        )

        if docs_vencidos or docs_proximo_vencer:
            content.append(Paragraph("<b>ALERTAS</b>", style_subtitle))

            alertas_data = [
                ["Tipo", "Documento", "Status", "Vencimento", "Recomendação"]
            ]

            style_normal = ParagraphStyle(
                "Normal",
                parent=styles["BodyText"],
                fontName="Helvetica",
                fontSize=9,
                leading=12,
                wordWrap="LTR",  # Quebra de palavras da esquerda para direita
            )

            style_tipo = ParagraphStyle(
                "TipoStyle",
                parent=styles["BodyText"],
                fontName="Helvetica",
                fontSize=7,  # Fonte menor
                leading=10,  # Espaçamento entre linhas ajustado
                wordWrap="LTR",  # Quebra de palavras
            )

            # Adiciona todos os documentos vencidos
            for doc in docs_vencidos:
                status = calcular_status(doc)
                alertas_data.append(
                    [
                        Paragraph(doc.tipo_documento or "Sem Tipo", style_tipo),
                        Paragraph(
                            doc.nome, style_normal
                        ),  # Usa Paragraph para permitir quebra de linha
                        "Vencido",
                        status["vencimento"],
                        "Revisão Imediata",
                    ]
                )

            # Adiciona todos os documentos próximos a vencer (até 30 dias)
            for doc in docs_proximo_vencer:
                status = calcular_status(doc)
                dias_restantes = (
                    parse_data(doc.vencimento) - datetime.now()
                ).days
                alertas_data.append(
                    [
                        Paragraph(doc.tipo_documento or "Sem Tipo", style_tipo),
                        Paragraph(doc.nome, style_normal),
                        f"Vence em {dias_restantes} dias",
                        status["vencimento"],
                        "Planejar Revisão",
                    ]
                )

            alertas_table = Table(
                alertas_data, colWidths=[3 * cm, 7 * cm, 3 * cm, 3 * cm, 3 * cm]
            )
            alertas_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#b22222")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        (
                            "VALIGN",
                            (0, 0),
                            (-1, -1),
                            "TOP",
                        ),  # Alinhamento vertical no topo
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8f9fa")),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.white, colors.HexColor("#f8f9fa")],
                        ),
                        ("TEXTCOLOR", (0, 1), (-1, -1), colors.black),
                        ("TEXTCOLOR", (2, 1), (2, -1), colors.red),
                        (
                            "WORDWRAP",
                            (1, 1),
                            (1, -1),
                            True,
                        ),  # Habilita quebra de palavras na coluna de documentos
                        ("LEADING", (0, 1), (-1, -1), 12),  # Espaçamento entre linhas
                        ("TOPPADDING", (0, 1), (-1, -1), 4),  # Espaçamento superior
                        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),  # Espaçamento inferior
                    ]
                )
            )

            content.append(alertas_table)
            content.append(Spacer(1, 16))

        # ========== SEÇÃO 3: RESUMO ESTATÍSTICO ==========
        content.append(Paragraph("<b>RESUMO ESTATÍSTICO</b>", style_subtitle))
        
        # Tabela de resumo reorganizada com melhor formatação
        resumo_data = [
            # Cabeçalho principal
            ["RELATÓRIO DE DOCUMENTOS", "TOTAL", "ATUALIZADOS", "DESATUALIZADOS"],
            
            # Linha de totais gerais (com destaque)
            [
                Paragraph("<b>TOTAL GERAL</b>", style_normal),
                str(total),
                Paragraph(f"<font color=green>{atualizados}</font> ({atualizados/total*100:.1f}%)", style_normal),
                Paragraph(f"<font color=red>{desatualizados}</font> ({desatualizados/total*100:.1f}%)", style_normal)
            ],
            
            # Separador visual melhorado
            ["", "", "", ""]  # Linha vazia como separador
        ]

        # Adicionar cada tipo de documento com formatação condicional
        for tipo, dados in sorted(contagem_por_tipo.items()):
            resumo_data.append([
                tipo,
                str(dados['total']),
                Paragraph(f"<font color=green>{dados['atualizados']}</font> ({dados['atualizados']/dados['total']*100:.1f}%)", style_normal),
                Paragraph(f"<font color=red>{dados['desatualizados']}</font> ({dados['desatualizados']/dados['total']*100:.1f}%)", style_normal)
            ])

        # Configuração final da tabela
        resumo_table = Table(resumo_data, colWidths=[8*cm, 2.5*cm, 4*cm, 4*cm])
        resumo_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor("#2c3e50")),  # Cabeçalho escuro
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, 1), HexColor("#e8f4fc")),  # Destaque para totais
            ('LINEBELOW', (0, 1), (-1, 1), 1, colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor("#dee2e6")),
            ('ROWBACKGROUNDS', (0, 2), (-1, -1), [colors.white, HexColor("#f8f9fa")]),
        ]))

        content.append(resumo_table)
        content.append(Spacer(1, 16))

        # QR Code e informações de contato
        base_url = "https://hg.huwc.ufc.br"  # Altere para sua URL de produção
        relatorio_url = f"{base_url}/miac/gerar_relatorio/{abrangencia}/{organograma}"

        # Gerar QR Code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=3,
            border=2,
        )
        qr.add_data(relatorio_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_img_buffer = BytesIO()
        qr_img.save(qr_img_buffer, format="PNG")
        qr_img_buffer.seek(0)

        # Criar tabela para rodapé com QR Code e informações
        footer_table = Table(
            [
                [
                    Image(qr_img_buffer, width=80, height=80),
                    Paragraph(
                        "<b>Módulo Integrado de Arquivos e Controle</b><br/>"
                        "Sistema de Gestão Documental - UGQ<br/>"
                        f"Relatório gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}<br/>"
                        "Escaneie o código ao lado para acessar a versão online",
                        style_footer,
                    ),
                ]
            ],
            colWidths=[4 * cm, 12 * cm],
        )

        footer_table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
                ]
            )
        )

        content.append(footer_table)

        # Gerar o PDF
        pdf_doc.build(content, onFirstPage=add_watermark, onLaterPages=add_watermark)

        buffer.seek(0)
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"Relatorio_{organograma}_{abrangencia}_{datetime.now().strftime('%Y%m%d')}.pdf",
            mimetype="application/pdf",
        )

    except Exception as e:
        logger.exception("Erro ao gerar relatório")
        return f"Erro ao gerar relatório: {str(e)}", 500


def add_watermark(canvas, doc):
    canvas.saveState()

    # Verifique se a imagem de fundo existe
    marca_fundo_path = os.path.join("static", "marca_fundo.png")
    if not os.path.exists(marca_fundo_path):
        logger.warning("Imagem de fundo %s não encontrada.", marca_fundo_path)
    else:
        canvas.setFillAlpha(0.05)
        canvas.drawImage(
            marca_fundo_path,
            x=0,
            y=200,
            width=letter[0],
            height=letter[1] * 0.75,
            preserveAspectRatio=True,
            mask="auto",
        )

    # Verifique se a imagem do cabeçalho existe
    marca_cabecalho_path = os.path.join("static", "marca_cabecalho.png")
    if not os.path.exists(marca_cabecalho_path):
        logger.warning("Imagem de cabeçalho %s não encontrada.", marca_cabecalho_path)
    else:
        canvas.setFillAlpha(1.0)
        canvas.drawImage(
            marca_cabecalho_path,
            x=200,
            y=720,
            width=400,
            height=100,
            preserveAspectRatio=True,
            mask="auto",
        )

    canvas.restoreState()


@app.route("/miac/login", methods=["GET", "POST"])
def login():
    if (
        "username" in session
    ):  # Se já estiver logado, redireciona para a página principal
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if login_user(username, password):
            session["username"] = username
            # Redireciona para a página principal após login
            return redirect(url_for("index"))
        else:
            return render_template("login.html", error="Usuário ou senha inválidos")

    return render_template("login.html")


@app.route("/miac/excluir_documento/<int:doc_id>/<tipo>", methods=["GET"])
def excluir_documento(doc_id, tipo):
    if "username" not in session:
        return redirect(url_for("login"))

    if tipo == "documento":
        documento = db.session.get(Documento, doc_id)
    elif tipo == "documento2":
        documento = db.session.get(Documento2, doc_id)
    else:
        return "Tipo de documento inválido", 400

    if documento is None:
        return "Documento não encontrado", 404

    db.session.delete(documento)
    db.session.commit()
    flash("Documento excluído com sucesso!", "success")

    if tipo == "documento":
        return redirect(url_for("publicados"))
    else:
        return redirect(url_for("publicados2"))


@app.route("/miac/lista")
def lista():
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template("lista.html")


# ========== NOVA ROTA PARA CARREGAR MODAL ========== #
@app.route("/miac/carregar_documentos_modal", methods=["GET"])
def carregar_documentos_modal():
    organograma = request.args.get("organograma", "").strip()
    abrangencia = request.args.get("abrangencia", "HUWC").strip()

    # Busca documentos específicos
    documentos = Documento2.query.filter_by(
        organograma=organograma, abrangencia=abrangencia
    ).all()

    # Agrupa por tipo de documento
    documentos_por_tipo = {}
    for doc in documentos:
        if doc.tipo_documento not in documentos_por_tipo:
            documentos_por_tipo[doc.tipo_documento] = []
        documentos_por_tipo[doc.tipo_documento].append(doc)

    return render_template(
        "partials/modal_content.html",  # Template que criamos antes
        organograma=organograma,
        documentos_por_tipo=documentos_por_tipo,
    )


# ========== FIM DA NOVA ROTA ========== #


@app.route("/miac/relacao")
def relacao():
    if "username" not in session:
        return redirect(url_for("login"))
    documentos = Documento.query.all()
    return render_template("relacao.html", documentos=documentos)


@app.route("/miac/relacao_documentos")
def relacao_documentos():
    if "username" not in session:
        return redirect(url_for("login"))

    documentos = Documento2.query.all()
    return render_template("relacao_documentos.html", documentos=documentos)


@app.route("/miac/buscar", methods=["GET"])
def buscar():
    if "username" not in session:
        return jsonify({"error": "Usuário não autenticado"}), 403

    titulo = request.args.get("titulo", "").strip()
    autor = request.args.get("autor", "").strip()
    data = request.args.get("data", "").strip()

    query = Documento.query

    if titulo:
        query = query.filter(Documento.titulo.ilike(f"%{titulo}%"))
    if autor:
        query = query.filter(Documento.elaboradores.ilike(f"%{autor}%"))
    if data:
        query = query.filter(Documento.data_publicacao == data)

    documentos = query.all()
    return render_template("partials/document_list.html", documentos=documentos)


@app.route("/miac/estatisticas", methods=["GET"])
def estatisticas():
    if "username" not in session:
        return redirect(url_for("login"))

    # Obter parâmetros de filtro
    abrangencia_filtro = request.args.get("abrangencia", "").strip()
    organograma_filtro = request.args.get("organograma", "").strip()
    tipo_documento_filtro = request.args.get("tipo_documento", "").strip()
    status_filtro = request.args.get("status", "").strip()

    # Consulta inicial
    query = Documento2.query

    # Aplicar filtros
    if abrangencia_filtro:
        query = query.filter(Documento2.abrangencia == abrangencia_filtro)
    if organograma_filtro:
        query = query.filter(Documento2.organograma == organograma_filtro)
    if tipo_documento_filtro:
        query = query.filter(Documento2.tipo_documento == tipo_documento_filtro)
    if status_filtro:
        if status_filtro == "atualizado":
            query = query.filter(Documento2.atualizado == True)
        elif status_filtro == "desatualizado":
            query = query.filter(Documento2.atualizado == False)

    documentos = query.all()

    # Calcula estatísticas gerais
    stats = {
        "total": len(documentos),
        "atualizados": sum(1 for doc in documentos if doc.atualizado),
        "desatualizados": sum(1 for doc in documentos if not doc.atualizado),
        "por_tipo": {},
        "por_abrangencia": {},
        "por_organograma": {},
        "por_marcador": {},
    }

    # Calcula estatísticas detalhadas
    for doc in documentos:
        # Por tipo de documento
        if doc.tipo_documento not in stats["por_tipo"]:
            stats["por_tipo"][doc.tipo_documento] = {
                "total": 0,
                "atualizados": 0,
                "desatualizados": 0,
            }
        stats["por_tipo"][doc.tipo_documento]["total"] += 1
        if doc.atualizado:
            stats["por_tipo"][doc.tipo_documento]["atualizados"] += 1
        else:
            stats["por_tipo"][doc.tipo_documento]["desatualizados"] += 1

        # Por abrangência
        if doc.abrangencia not in stats["por_abrangencia"]:
            stats["por_abrangencia"][doc.abrangencia] = {
                "total": 0,
                "atualizados": 0,
                "desatualizados": 0,
            }
        stats["por_abrangencia"][doc.abrangencia]["total"] += 1
        if doc.atualizado:
            stats["por_abrangencia"][doc.abrangencia]["atualizados"] += 1
        else:
            stats["por_abrangencia"][doc.abrangencia]["desatualizados"] += 1

        # Por organograma
        if doc.organograma not in stats["por_organograma"]:
            stats["por_organograma"][doc.organograma] = {
                "total": 0,
                "atualizados": 0,
                "desatualizados": 0,
            }
        stats["por_organograma"][doc.organograma]["total"] += 1
        if doc.atualizado:
            stats["por_organograma"][doc.organograma]["atualizados"] += 1
        else:
            stats["por_organograma"][doc.organograma]["desatualizados"] += 1

        # Por marcador
        marcador = doc.marcador if doc.marcador else "Sem Marcador"
        if marcador not in stats["por_marcador"]:
            stats["por_marcador"][marcador] = {
                "total": 0,
                "atualizados": 0,
                "desatualizados": 0,
            }
        stats["por_marcador"][marcador]["total"] += 1
        if doc.atualizado:
            stats["por_marcador"][marcador]["atualizados"] += 1
        else:
            stats["por_marcador"][marcador]["desatualizados"] += 1

    notificacoes = verificar_vencimentos()

    # Identifica documentos com erro
    documentos_com_erro = identificar_documentos_com_erro()

    # Renderiza o template com as estatísticas, notificações e documentos com erro
    return render_template(
        "estatisticas.html",
        stats=stats,
        notificacoes=notificacoes,
        documentos_com_erro=documentos_com_erro,
        abrangencias=Documento2.query.with_entities(Documento2.abrangencia).distinct(),
        organogramas=Documento2.query.with_entities(Documento2.organograma).distinct(),
        tipos_documento=Documento2.query.with_entities(
            Documento2.tipo_documento
        ).distinct(),
    )


def verificar_vencimentos():
    """Retorna lista de notificações sobre documentos vencidos ou próximos do vencimento."""
    documentos = Documento2.query.filter(Documento2.vencimento.isnot(None)).all()
    notificacoes = []
    for doc in documentos:
        try:
            data_vencimento = parse_data(doc.vencimento).date()
            hoje = datetime.now().date()
            dias_restantes = (data_vencimento - hoje).days
            if 0 <= dias_restantes <= 30:
                notificacoes.append(f"Documento '{doc.nome}' vence em {dias_restantes} dias.")
            elif dias_restantes < 0:
                notificacoes.append(f"Documento '{doc.nome}' está vencido há {-dias_restantes} dias.")
        except ValueError:
            continue
    return notificacoes


def identificar_documentos_com_erro():
    documentos_com_erro = []

    # Consulta todos os documentos
    documentos = Documento2.query.all()

    for documento in documentos:
        erros = []

        # Verifica se a data de vencimento é válida
        if documento.vencimento:
            try:
                converter_data(documento.vencimento)
            except ValueError:
                erros.append(f"Data de vencimento inválida: {documento.vencimento}")

        # Verifica campos obrigatórios
        if not documento.organograma:
            erros.append("Organograma não informado")
        if not documento.tipo_documento:
            erros.append("Tipo de documento não informado")
        if not documento.abrangencia:
            erros.append("Abrangência não informada")

        # Se houver erros, adiciona o documento à lista de documentos com erro
        if erros:
            documentos_com_erro.append({"documento": documento, "erros": erros})

    return documentos_com_erro


@app.route("/miac/buscar2", methods=["GET"])
def buscar2():
    # Obter parâmetros de pesquisa
    nome = request.args.get("nome", "").strip()
    organograma = request.args.get("organograma", "").strip()
    tipo_documento = request.args.get("tipo_documento", "").strip()
    abrangencia = request.args.get("abrangencia", "HUWC").strip()
    apenas_complexo = request.args.get("apenas_complexo", "false") == "true"
    search_organograma = request.args.get("search_organograma", "").strip().lower()

    # Iniciar a query
    query = Documento2.query

    # Aplicar filtros
    if nome:
        termo_busca = normalizar_texto(nome)
        query = query.filter(db.func.unaccent(Documento2.nome).ilike(f"%{termo_busca}%"))

    if organograma:
        termo_busca = normalizar_texto(organograma)
        query = query.filter(or_(
            db.func.unaccent(Documento2.organograma).ilike(f"%{termo_busca}%"),
            db.func.unaccent(Documento2.nome_completo).ilike(f"%{termo_busca}%")
        ))
        
    if tipo_documento:
        termo_busca = normalizar_texto(tipo_documento)
        query = query.filter(db.func.unaccent(Documento2.tipo_documento).ilike(f"%{termo_busca}%"))

    if abrangencia:
        query = query.filter(Documento2.abrangencia == abrangencia)

    if apenas_complexo:
        query = query.filter(or_(
            Documento2.nome.like("%CH.%"),
            Documento2.nome.like("%CHUFC.%")
          
        ))

    # Executar a query
    documentos = query.all()

    if search_organograma:
        documentos = [
            doc for doc in documentos 
            if (search_organograma in normalizar_texto(doc.organograma) or 
               (doc.nome_completo and search_organograma in normalizar_texto(doc.nome_completo)))
        ]

    documentos_agrupados = {}
    if not (nome or organograma or tipo_documento or search_organograma or apenas_complexo):
        for doc in documentos:
            marcador = doc.marcador if doc.marcador else "Sem Marcador"
            if marcador not in documentos_agrupados:
                documentos_agrupados[marcador] = {}
            if doc.organograma not in documentos_agrupados[marcador]:
                documentos_agrupados[marcador][doc.organograma] = {}
            if doc.tipo_documento not in documentos_agrupados[marcador][doc.organograma]:
                documentos_agrupados[marcador][doc.organograma][doc.tipo_documento] = []
            documentos_agrupados[marcador][doc.organograma][doc.tipo_documento].append(doc)

    # Buscar organogramas únicos
    organogramas_completos = db.session.query(
        Documento2.organograma,
        Documento2.nome_completo
    ).distinct().all()

    organogramas_formatados = [
        {"sigla": org[0], "nome_completo": org[1]} 
        for org in organogramas_completos
    ]
    
    # Ordenação corrigida
    organogramas_formatados.sort(key=lambda x: (x["nome_completo"] or x["sigla"]).lower())

    tipos_documento_unicos = set(doc.tipo_documento for doc in documentos if doc.tipo_documento)
    tipos_documento = sorted(list(tipos_documento_unicos))

    return render_template(
        "partials/document_list2.html",
        documentos_agrupados=documentos_agrupados,
        documentos=documentos,
        exibir_lista=bool(nome or organograma or tipo_documento or search_organograma or apenas_complexo),
        abrangencia=abrangencia,
        organogramas=organogramas_formatados,
        tipos_documento=tipos_documento,
        organograma_filtro=organograma,
        tipo_documento_filtro=tipo_documento
    )

def normalizar_texto(texto):
    """Remove acentos e converte para minúsculas"""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    return texto.lower()

@app.route("/miac/logout")
def logout():
    session.pop("username", None)  # Remove o usuário da sessão
    return redirect(url_for("login"))


@app.route("/miac/", methods=["GET", "POST"])
def index():
    if "username" not in session:
        return redirect(url_for("login"))

    titulo = request.args.get("titulo", "")
    autor_id = request.args.get("autor", "")
    data = request.args.get("data", "")

    query = Documento.query

    if titulo:
        query = query.filter(Documento.titulo.ilike(f"%{titulo}%"))
    if autor_id:
        query = query.filter(Documento.elaboradores.ilike(f"%{autor_id}%"))
    if data:
        query = query.filter(Documento.data_publicacao == data)

    documentos = query.all()
    return render_template("index.html", documentos=documentos)


def read_last_page(file_path):
    """
    Versão simplificada que:
    - Extrai apenas o texto da última página
    - Não usa OCR ou validação por regex
    """
    try:
        doc = fitz.open(file_path)
        num_pages = len(doc)
        
        # Pega apenas a última página
        page = doc.load_page(-1)
        text = page.get_text("text")
        cleaned_text = clean_text(text)
        
        return cleaned_text if cleaned_text.strip() else None

    except Exception as e:
        logger.error("Erro ao ler última página do PDF: %s", e)
        return None
    finally:
        if "doc" in locals():
            doc.close()

def clean_text(text):
    """Remove caracteres errados e normaliza espaços"""
    return re.sub(r"\s+", " ", text).strip()

def send_to_deepseek_with_retry(prompt, api_key, retries=3, delay=2):
    for i in range(retries):
        try:
            url = "https://api.deepseek.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            data = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
            }

            response = requests.post(url, headers=headers, json=data)

            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                logger.warning("DeepSeek tentativa %d falhou: %s %s", i + 1, response.status_code, response.text)

        except Exception as e:
            logger.warning("DeepSeek tentativa %d falhou: %s", i + 1, e)

        time.sleep(delay)
    return None

def send_to_gpt_with_retry(prompt, api_key, retries=3, delay=2):
    for i in range(retries):
        try:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            data = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
            }
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                logger.warning("ChatGPT tentativa %d falhou: %s %s", i + 1, response.status_code, response.text)
        except Exception as e:
            logger.warning("ChatGPT tentativa %d falhou: %s", i + 1, e)
        time.sleep(delay)
    return None

@app.route("/miac/gerenciar_siglas", methods=["GET", "POST"])
def gerenciar_siglas():
    if "username" not in session or session.get("nivel_acesso") != "elevado":
        return redirect(url_for("login"))

    siglas_com_contagem = db.session.query(
        Documento2.organograma,
        db.func.max(Documento2.nome_completo).label('nome_completo'),
        db.func.count(Documento2.id).label('total_documentos')
    ).group_by(Documento2.organograma).all()

    if request.method == "POST":
        sigla = request.form.get("sigla").strip().upper()
        nome_completo = request.form.get("nome_completo").strip()

        Documento2.query.filter_by(organograma=sigla).update({
            "nome_completo": nome_completo
        })
        db.session.commit()
        flash("Sigla atualizada com sucesso!", "success")
        return redirect(url_for("gerenciar_siglas"))

    return render_template("gerenciar_siglas.html", 
                         siglas=siglas_com_contagem)

@app.route("/miac/obter-dados", methods=["POST"])
def obter_dados():
    if "username" not in session:
        return jsonify({"error": "Usuário não autenticado"}), 403

    try:
        files = request.files.getlist("pdf_file")
        modelo_ia = request.form.get("modelo_ia", "deepseek")

        if not files:
            return jsonify({"error": "Nenhum arquivo enviado."}), 400

        resultados = []
        for file in files:
            if file.filename == "" or not file.filename.lower().endswith(".pdf"):
                continue

            tentativa = 0
            sucesso = False
            file_path = None

            while tentativa < 3 and not sucesso:
                try:
                    file_name = f"{int(time.time())}_{secure_filename(file.filename)}"
                    file_path = os.path.join(UPLOAD_FOLDER2, file_name).replace("\\", "/")
                    file.save(file_path)

                    pdf_text = read_last_page(file_path)

                    if pdf_text is None or len(pdf_text.strip()) < 20:
                        raise Exception(f"Texto não encontrado ou insuficiente no PDF: {file.filename}")

                    # PROMPT ORIGINAL
                    prompt = (
                        f"Por favor, extraia as seguintes informações do texto de forma literal. "
                        f"Retorne apenas o valor encontrado ou 'Não localizado' se não houver correspondência. "
                        f"Não use alternativas aproximadas.\n"
                        f"Data de Elaboração (tem que ser no formato dd/mm/aaaa se encontrar dd.mm.aaaa mande no formato que eu disse:\n"
                        f"Vencimento (também pode ser identificado como 'Revisão' mande nesse formato dd/mm/aaaa sempre mesmo se tiver no formato dd.mm.aaaa, pq as vezes voce pode achar dd.mm.aaaa, se não achar, a data de vencimento é 2 a mais do que a de elaboração aaaa+2):\n"
                        f"Organograma (se o formato for EX:'POP.UAP-CHUFC.006', 'UAP' é o Organograma. "
                        f"Se o formato for EX 'PRO.MED-OBS-MEAC.013', 'MED-OBS' é o Organograma. "
                        f"Caso o código do documento seja EX'FOR.DIVGP-CHUFC.005', 'DIVGP' é o Organograma. "
                        f"Os outros códigos serão parecidos com esse, entendeu? Serão nesse formato, códigos genéricos):\n"
                        f"Tipo de Documento (RETORNE EM CAIXA ALTA, se aparer FOR é FORMULÁRIO, SE APARECER POP É PROCEDIMENTO OPERACIONAL PADRÃO, MANDE COMPLETO):\n"
                        f"Abrangência (se a sigla final for 'CHUFC' ou 'CH', retorne 'HUWC'. "
                        f"Se for 'MEAC' ou 'HUWC', mantenha a sigla encontrada, ou seja, no final só pode ser MEAC ou HUWC):\n"
                        f"Código do Documento (ex.: 'FOR.DIVGP-CHUFC.005'):\n"
                        f"Título do Documento:\n"
                        f"Número SEI (é tipo esse o SEI nº 23533.003368/2023-10):\n"
                        f"Elaboradores (separe por vírgula caso tenha mais de um):\n"
                        f"Texto:\n{pdf_text}"
                    )

                    if modelo_ia == "deepseek":
                        gpt_response = send_to_deepseek_with_retry(prompt, DEEPSEEK_API_KEY)
                    elif modelo_ia == "chatgpt":
                        gpt_response = send_to_gpt_with_retry(prompt, CHATGPT_API_KEY)
                    else:
                        return jsonify({"error": "Modelo de IA inválido"}), 400

                    if gpt_response is None:
                        raise Exception(f"Erro ao comunicar com a API de IA para o arquivo: {file.filename}")

                    lines = [line.strip() for line in gpt_response.split("\n") if line.strip()]

                    extracted_data = {
                        "data_elaboracao": "Não localizado",
                        "vencimento": "Não localizado",
                        "numero_sei": "Não localizado",
                        "organograma": "Não localizado",
                        "tipo_documento": "Não localizado",
                        "abrangencia": "Não localizado",
                        "codigo_documento": "Não localizado",
                        "titulo_documento": file.filename,
                        "elaboradores": "Não localizado",
                    }

                    for line in lines:
                        if "Data de Elaboração:" in line:
                            extracted_data["data_elaboracao"] = line.split(":", 1)[1].strip()
                        elif "Vencimento:" in line or "Revisão:" in line:
                            extracted_data["vencimento"] = line.split(":", 1)[1].strip()
                        elif "Número SEI:" in line:
                            extracted_data["numero_sei"] = line.split(":", 1)[1].strip()
                        elif "Organograma:" in line:
                            extracted_data["organograma"] = line.split(":", 1)[1].strip()
                        elif "Tipo de Documento:" in line:
                            extracted_data["tipo_documento"] = line.split(":", 1)[1].strip()
                        elif "Abrangência:" in line:
                            extracted_data["abrangencia"] = line.split(":", 1)[1].strip()
                        elif "Código do Documento:" in line:
                            extracted_data["codigo_documento"] = line.split(":", 1)[1].strip()
                        elif "Título do Documento:" in line:
                            extracted_data["titulo_documento"] = line.split(":", 1)[1].strip()
                        elif "Elaboradores:" in line:
                            elaboradores = line.split(":", 1)[1].strip()
                            extracted_data["elaboradores"] = [e.strip() for e in elaboradores.split(",")]

                    titulo_completo = f"{extracted_data['codigo_documento']} - {extracted_data['titulo_documento']}" if (
                        extracted_data["codigo_documento"] != "Não localizado" and 
                        extracted_data["titulo_documento"] != file.filename
                    ) else file.filename

                    resultados.append({
                        "gpt_response": {
                            "data_elaboracao": extracted_data["data_elaboracao"],
                            "vencimento": extracted_data["vencimento"],
                            "numero_sei": extracted_data["numero_sei"],
                            "titulo": titulo_completo,
                            "organograma": extracted_data["organograma"],
                            "tipo_documento": extracted_data["tipo_documento"],
                            "abrangencia": extracted_data["abrangencia"],
                            "texto_extraido": pdf_text[:200] + "..." if len(pdf_text) > 200 else pdf_text,
                        },
                        "elaboradores": extracted_data["elaboradores"] if isinstance(extracted_data["elaboradores"], list) else [extracted_data["elaboradores"]],
                        "status": "sucesso",
                    })

                    sucesso = True

                except Exception as e:
                    tentativa += 1
                    if tentativa == 3:
                        resultados.append({
                            "titulo": file.filename,
                            "status": f"Erro após 3 tentativas: {str(e)}",
                            "texto_extraido": pdf_text[:200] + "..." if pdf_text and len(pdf_text) > 200 else (pdf_text if pdf_text else "Nenhum texto extraído"),
                        })
                    time.sleep(1)

                finally:
                    if file_path and os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except Exception as e:
                            logger.warning("Erro ao remover arquivo temporário: %s", e)

        return jsonify(resultados)

    except Exception as e:
        logger.exception("Erro ao processar arquivos")
        return jsonify({"error": f"Erro ao processar arquivos: {str(e)}"}), 500



def converter_data(data):
    """Retorna date object a partir de string."""
    return parse_data(data).date()


def atualizar_status_documentos():
    documentos = Documento2.query.all()
    for documento in documentos:
        if documento.vencimento:
            try:
                data_vencimento = converter_data(documento.vencimento)
                documento.atualizado = data_vencimento >= datetime.now().date()
            except ValueError as e:
                logger.warning("Erro ao converter data do documento %d: %s", documento.id, e)

    db.session.commit()


@app.template_filter("expired_duration")
def expired_duration(vencimento):
    try:
        # Supondo que a data esteja no formato 'dd/mm/yyyy'
        exp_date = datetime.strptime(vencimento, "%d/%m/%Y")
    except ValueError:
        try:
            # Caso esteja no formato 'yyyy-mm-dd'
            exp_date = datetime.strptime(vencimento, "%Y-%m-%d")
        except Exception:
            return ""
    diff = datetime.now() - exp_date
    days = diff.days
    if days < 30:
        return f"{days} dia{'s' if days != 1 else ''}"
    elif days < 365:
        months = days // 30
        return f"{months} mês{'es' if months != 1 else ''}"
    else:
        years = days // 365
        return f"{years} ano{'s' if years != 1 else ''}"


@app.route("/miac/publicar2", methods=["POST"])
def publicar2():
    if "username" not in session:
        return jsonify({"error": "Usuário não autenticado"}), 403

    try:
        # Recebe os arquivos (PDF ou Word)
        files = request.files.getlist("pdf_file")

        # Recebe os dados do formulário como arrays
        titulos = request.form.getlist("titulo[]")
        organogramas = request.form.getlist("organograma[]")
        tipos_documento = request.form.getlist("tipo_documento[]")
        abrangencias = request.form.getlist("abrangencia[]")
        elaboradores_lista = request.form.getlist("elaboradores[]")
        numeros_sei = request.form.getlist("numero_sei[]")
        vencimentos = request.form.getlist("vencimento[]")
        datas_elaboracao = request.form.getlist("data_elaboracao[]")

        # Verifica se o número de títulos corresponde ao número de arquivos
        if len(titulos) != len(files):
            logger.warning("Número de títulos (%d) não corresponde ao número de arquivos (%d)", len(titulos), len(files))
            return (
                jsonify(
                    {
                        "error": "Número de títulos não corresponde ao número de arquivos."
                    }
                ),
                400,
            )

        # Verifica se todos os campos têm o mesmo número de elementos
        if not (
            len(organogramas)
            == len(tipos_documento)
            == len(abrangencias)
            == len(elaboradores_lista)
            == len(numeros_sei)
            == len(vencimentos)
            == len(datas_elaboracao)
            == len(files)
        ):
            return (
                jsonify(
                    {"error": "Número de campos não corresponde ao número de arquivos."}
                ),
                400,
            )

        log_detalhado = []

        # Processa cada arquivo e salva no banco de dados
        for index, file in enumerate(files):
            filename_lower = file.filename.lower()
            
            # Verifica se é um arquivo permitido (PDF, DOC ou DOCX)
            if not (filename_lower.endswith('.pdf') or 
                   filename_lower.endswith('.doc') or 
                   filename_lower.endswith('.docx')):
                continue

            # Gera um nome seguro e adiciona identificador único
            base_nome = secure_filename(titulos[index].replace(" ", "_"))
            file_ext = os.path.splitext(file.filename)[1].lower()
            file_name = f"{base_nome}_{int(time.time())}{file_ext}"

            file_path = os.path.join(UPLOAD_FOLDER2, file_name).replace("\\", "/")

            # Verifica se já existe um arquivo com o mesmo nome
            contador = 1
            while os.path.exists(file_path):
                file_name = f"{base_nome}_{int(time.time())}_v{contador}{file_ext}"
                file_path = os.path.join(UPLOAD_FOLDER2, file_name).replace(
                    "\\", "/"
                )
                contador += 1

            file.save(file_path)

            # Verifica se já existe um marcador para este organograma e abrangência
            marcador = None
            documento_existente = Documento2.query.filter_by(
                organograma=organogramas[index],
                abrangencia=abrangencias[index]
            ).first()
            
            if documento_existente and documento_existente.marcador:
                marcador = documento_existente.marcador

            # Verifica se já existe um nome_completo para este organograma
            nome_completo = None
            documento_com_nome = Documento2.query.filter_by(
                organograma=organogramas[index]
            ).first()
            
            if documento_com_nome and documento_com_nome.nome_completo:
                nome_completo = documento_com_nome.nome_completo

            # Cria um novo documento no banco de dados
            documento = Documento2(
                nome=titulos[index],
                organograma=organogramas[index],
                tipo_documento=tipos_documento[index],
                abrangencia=abrangencias[index],
                atualizado=True,
                data_elaboracao=datas_elaboracao[index],
                vencimento=vencimentos[index],
                numero_sei=numeros_sei[index],
                elaboradores=elaboradores_lista[index],
                caminho=file_path,
                data_publicacao=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                marcador=marcador,  # Associa o marcador se existir
                nome_completo=nome_completo  # Associa o nome_completo se existir
            )
            db.session.add(documento)

            # Adiciona ao log detalhado
            log_detalhado.append(f"{titulos[index]} salvo como {file_name}")

        # Salva as alterações no banco de dados
        db.session.commit()

        for log in log_detalhado:
            logger.info("Publicação: %s", log)

        return jsonify({"message": "Documentos publicados com sucesso!"})

    except Exception as e:
        logger.exception("Erro ao publicar documentos")
        return (
            jsonify({"error": f"Erro ao publicar documentos. Detalhes: {str(e)}"}),
            500,
        )


@app.route("/miac/publicados", methods=["GET"])
def publicados():
    if "username" not in session:
        return redirect(url_for("login"))

    documentos = Documento.query.all()
    return render_template("publicados.html", documentos=documentos)


@app.route("/miac/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)


@app.route("/miac/documento/<int:doc_id>", methods=["GET"])
def documento_detalhes(doc_id):

    documento = db.session.get(Documento, doc_id)
    if documento:
        # Gerar o link para o arquivo PDF
        documento_url = url_for(
            "static",
            filename=f"uploads2/{os.path.basename(documento.caminho)}",
            _external=True,
        )
        return render_template(
            "detalhes_documento.html", documento=documento, documento_url=documento_url
        )
    else:
        return "Documento não encontrado", 404


@app.route("/miac/publicados2", methods=["GET"])
def publicados2():
    # Atualiza o status dos documentos antes de exibi-los
    atualizar_status_documentos()

    # Obter parâmetros de filtro
    abrangencia_selecionada = request.args.get("abrangencia", "HUWC")
    organograma_filtro = request.args.get("organograma", "").strip()
    tipo_documento_filtro = request.args.get("tipo_documento", "").strip()

    # Filtra documentos pela abrangência selecionada
    query = Documento2.query.filter_by(abrangencia=abrangencia_selecionada)

    # Aplicar filtros adicionais (organograma e tipo de documento)
    if organograma_filtro:
        query = query.filter(Documento2.organograma == organograma_filtro)
    if tipo_documento_filtro:
        query = query.filter(Documento2.tipo_documento == tipo_documento_filtro)

    # Executar a query
    documentos = query.all()

    # Agrupar documentos por marcador, organograma e tipo de documento
    documentos_agrupados = {}
    tipos_documento_unicos = set()

    for documento in documentos:
        # Verifica se o marcador existe; caso contrário, usa "Sem Marcador"
        marcador = documento.marcador if documento.marcador else "Sem Marcador"

        # Estrutura de agrupamento: {marcador: {organograma: {tipo_documento: [documentos]}}}
        if marcador not in documentos_agrupados:
            documentos_agrupados[marcador] = {}
        if documento.organograma not in documentos_agrupados[marcador]:
            documentos_agrupados[marcador][documento.organograma] = {}
        if (
            documento.tipo_documento
            not in documentos_agrupados[marcador][documento.organograma]
        ):
            documentos_agrupados[marcador][documento.organograma][
                documento.tipo_documento
            ] = []
        documentos_agrupados[marcador][documento.organograma][
            documento.tipo_documento
        ].append(documento)

        # Adiciona valores únicos para tipos de documento
        if documento.tipo_documento:
            tipos_documento_unicos.add(documento.tipo_documento)

    # Busca organogramas únicos COM nome_completo
    organogramas_completos = db.session.query(
        Documento2.organograma,
        Documento2.nome_completo
    ).distinct().all()

    # Organiza em uma lista de dicionários e ordena por nome_completo ou sigla
    organogramas_formatados = [
        {"sigla": org[0], "nome_completo": org[1]} 
        for org in organogramas_completos
    ]
    organogramas_formatados.sort(key=lambda x: (x["nome_completo"] or "").lower() or x["sigla"].lower())

    # Converter conjunto de tipos de documento para lista ordenada
    tipos_documento = sorted(list(tipos_documento_unicos))

    return render_template(
        "publicados2.html",
        documentos_agrupados=documentos_agrupados,
        organogramas=organogramas_formatados,
        tipos_documento=tipos_documento,
        abrangencia_selecionada=abrangencia_selecionada,
        organograma_filtro=organograma_filtro,
        tipo_documento_filtro=tipo_documento_filtro,
    )

@app.route("/miac/documento2/<int:doc_id>", methods=["GET"])
def documento2_detalhes(doc_id):

    documento = db.session.get(Documento2, doc_id)
    if documento:
        documento_url = url_for(
            "static",
            filename=f"uploads2/{os.path.basename(documento.caminho)}",
            _external=True,
        )
        return render_template(
            "detalhes2_documentos.html",
            documento=documento,
            documento_url=documento_url,
            nivel_acesso=session.get("nivel_acesso"),
        )
    else:
        return "Documento não encontrado", 404


@app.route("/miac/gerenciar_marcadores", methods=["GET", "POST"])
def gerenciar_marcadores():
    if "username" not in session or session.get("nivel_acesso") != "elevado":
        return redirect(url_for("login"))

    if request.method == "POST":
        for key, value in request.form.items():
            if key.startswith("marcador_"):
                parts = key.split("_")
                organograma_nome = parts[1]
                abrangencia = parts[2]

                Documento2.query.filter_by(
                    organograma=organograma_nome, abrangencia=abrangencia
                ).update({"marcador": value})

        # Adicionar novos marcadores se necessário
        novo_organograma = request.form.get("novo_organograma")
        novo_abrangencia = request.form.get("novo_abrangencia")
        novo_marcador = request.form.get("novo_marcador")

        if novo_organograma and novo_abrangencia and novo_marcador:
            Documento2.query.filter_by(
                organograma=novo_organograma, abrangencia=novo_abrangencia
            ).update({"marcador": novo_marcador})

        db.session.commit()
        flash("Marcadores atualizados com sucesso!", "success")
        return redirect(url_for("gerenciar_marcadores"))

    # Buscar organogramas únicos + abrangência
    organogramas_unicos = (
        db.session.query(
            Documento2.organograma, Documento2.abrangencia, Documento2.marcador
        )
        .distinct()
        .all()
    )

    return render_template(
        "gerenciar_marcadores.html", organogramas=organogramas_unicos
    )


@app.route("/miac/editar_documento2/<int:doc_id>", methods=["GET", "POST"])
def editar_documento2(doc_id):
    # Verificação de autenticação e autorização
    if "username" not in session or session.get("nivel_acesso") != "elevado":
        return redirect(url_for("login"))

    documento = db.session.get(Documento2, doc_id)
    if not documento:
        return "Documento não encontrado", 404

    if request.method == "POST":
        try:

            # Atualização dos campos básicos
            documento.nome = request.form.get("nome", documento.nome)
            documento.organograma = request.form.get(
                "organograma", documento.organograma
            )
            documento.tipo_documento = request.form.get(
                "tipo_documento", documento.tipo_documento
            )
            documento.abrangencia = request.form.get(
                "abrangencia", documento.abrangencia
            )
            documento.atualizado = request.form.get("atualizado") == "on"
            documento.data_elaboracao = request.form.get(
                "data_elaboracao", documento.data_elaboracao
            )
            documento.vencimento = request.form.get("vencimento", documento.vencimento)
            documento.numero_sei = request.form.get("numero_sei", documento.numero_sei)
            documento.elaboradores = request.form.get(
                "elaboradores", documento.elaboradores
            )

            # Processamento de novo arquivo PDF
            if "novo_pdf" in request.files and request.files["novo_pdf"].filename != "":
                novo_pdf = request.files["novo_pdf"]

                if novo_pdf.filename.lower().endswith(".pdf"):
                    # Inicialização do histórico
                    if documento.historico_versoes is None:
                        documento.historico_versoes = MutableList()
                    elif not isinstance(documento.historico_versoes, MutableList):
                        documento.historico_versoes = MutableList(
                            documento.historico_versoes
                        )

                    # Criação da nova entrada no histórico
                    historico_entry = {
                        "versao": documento.versao_atual if documento.versao_atual is not None else 1,
                        "caminho": documento.caminho,
                        "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                        "responsavel": session["username"],
                        "nome_arquivo": os.path.basename(documento.caminho) if documento.caminho else None,
                    }

                    # Adição ao histórico e atualização da versão
                    documento.historico_versoes.append(historico_entry)
                    documento.versao_atual = (documento.versao_atual or 1) + 1

                    # Salvamento do novo arquivo
                    file_name = f"doc_{doc_id}_v{documento.versao_atual}_{int(time.time())}.pdf"
                    file_path = os.path.join(UPLOAD_FOLDER2, file_name)
                    novo_pdf.save(file_path)
                    logger.info("Novo PDF do documento %d salvo em %s", doc_id, file_path)

                    # Atualização dos caminhos
                    documento.pdf_antigo = documento.caminho
                    documento.caminho = file_path.replace("\\", "/")
                    documento.data_atualizacao = datetime.now()

            # Commit das alterações
            db.session.commit()
            flash("Documento atualizado com sucesso!", "success")
            return redirect(url_for("documento2_detalhes", doc_id=doc_id))

        except Exception as e:
            db.session.rollback()
            logger.exception("Erro ao atualizar documento %d", doc_id)
            flash(f"Erro ao atualizar documento: {str(e)}", "error")
            return redirect(url_for("editar_documento2", doc_id=doc_id))

    # Preparação dos dados para o template (GET)
    historico = []
    if documento.historico_versoes:
        if isinstance(documento.historico_versoes, (MutableList, list)):
            historico = list(documento.historico_versoes)
        elif isinstance(documento.historico_versoes, str):
            try:
                historico = json.loads(documento.historico_versoes)
            except json.JSONDecodeError:
                historico = []

    try:
        historico_ordenado = sorted(
            [h for h in historico if isinstance(h, dict) and "versao" in h],
            key=lambda x: x["versao"],
            reverse=True,
        )
    except Exception as e:
        logger.warning("Erro ao ordenar histórico do documento %d: %s", doc_id, e)
        historico_ordenado = []

    dados_template = {
        "documento": documento,
        "versao_efetiva": documento.versao_atual if documento.versao_atual is not None else 1,
        "historico_efetivo": historico_ordenado,
        "data_elaboracao": formatar_data_para_input(documento.data_elaboracao),
        "vencimento": formatar_data_para_input(documento.vencimento),
    }

    return render_template("editar_documento2.html", **dados_template)


def formatar_data_para_input(data_str):
    """Converte data para formato yyyy-mm-dd (input type='date')."""
    if not data_str:
        return ""
    try:
        return parse_data(data_str).strftime("%Y-%m-%d")
    except ValueError:
        return ""


@app.route("/miac/restaurar_versao/<int:doc_id>/<int:versao>", methods=["POST"])
def restaurar_versao(doc_id, versao):
    if "username" not in session or session.get("nivel_acesso") != "elevado":
        return jsonify({"success": False, "error": "Acesso negado"}), 403

    documento = db.session.get(Documento2, doc_id)
    if not documento:
        return jsonify({"success": False, "error": "Documento não encontrado"}), 404

    try:
        # Obter histórico (com tratamento para documentos antigos)
        historico = (
            documento.historico_versoes
            if documento.historico_versoes is not None
            else []
        )

        # Encontrar a versão a ser restaurada
        versao_restaurar = next((v for v in historico if v["versao"] == versao), None)

        if not versao_restaurar:
            return (
                jsonify({"success": False, "error": f"Versão {versao} não encontrada"}),
                404,
            )

        # Registrar a versão atual no histórico
        nova_entrada_historico = {
            "versao": (
                documento.versao_atual if documento.versao_atual is not None else 1
            ),
            "caminho": documento.caminho,
            "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "responsavel": session["username"],
            "nome_arquivo": os.path.basename(documento.caminho),
        }
        historico.append(nova_entrada_historico)

        # Atualizar documento
        documento.versao_atual = versao
        documento.historico_versoes = [v for v in historico if v["versao"] != versao]
        documento.pdf_antigo = documento.caminho
        documento.caminho = versao_restaurar["caminho"]
        documento.data_publicacao = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        db.session.commit()
        return jsonify(
            {"success": True, "message": f"Versão {versao} restaurada com sucesso!"}
        )

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/miac/publicar2", methods=["GET"])
def publicar2_page():
    if "username" not in session:
        return redirect(url_for("login"))

    # Busca valores únicos DIRETAMENTE da tabela Documento2
    organogramas = db.session.query(Documento2.organograma).distinct().all()
    tipos_documento = db.session.query(Documento2.tipo_documento).distinct().all()
    abrangencias = db.session.query(Documento2.abrangencia).distinct().all()

    return render_template(
        "publicar2.html",
        organogramas=[org[0] for org in organogramas if org[0]],  # Remove valores nulos
        tipos_documento=[tipo[0] for tipo in tipos_documento if tipo[0]],
        abrangencias=[abrang[0] for abrang in abrangencias if abrang[0]]
    )

@app.route("/miac/gerenciar_opcoes", methods=["GET", "POST"])
def gerenciar_opcoes():
    if "username" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        tipo = request.form.get("tipo")
        nome = request.form.get("nome")

        if tipo == "organograma":
            novo_organograma = Organograma(nome=nome)
            db.session.add(novo_organograma)
        elif tipo == "tipo_documento":
            novo_tipo_documento = TipoDocumento(nome=nome)
            db.session.add(novo_tipo_documento)

        db.session.commit()
        return redirect(url_for("gerenciar_opcoes"))

    organogramas = Organograma.query.all()
    tipos_documento = TipoDocumento.query.all()

    return render_template(
        "gerenciar_opcoes.html",
        organogramas=organogramas,
        tipos_documento=tipos_documento,
    )


@app.route("/miac/remover_opcao/<int:id>/<tipo>")
def remover_opcao(id, tipo):
    if "username" not in session:
        return redirect(url_for("login"))

    if tipo == "organograma":
        opcao = Organograma.query.get(id)
    elif tipo == "tipo_documento":
        opcao = TipoDocumento.query.get(id)

    if opcao:
        db.session.delete(opcao)
        db.session.commit()

    return redirect(url_for("gerenciar_opcoes"))


if __name__ == "__main__":
    with app.app_context():
        inspector = inspect(db.engine)
        if not inspector.has_table("documento2"):
            db.create_all()

    logger.info("Iniciando servidor na porta 8090")
    serve(app, host="0.0.0.0", port=8090)
