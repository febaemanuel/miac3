"""Rotas de relatórios: PDF consolidado e dashboard de estatísticas."""
import logging
import os
from datetime import datetime
from io import BytesIO

logger = logging.getLogger(__name__)

import qrcode
from flask import (
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models import Documento2, OrganizacaoConfig
from app.services.dates import converter_data, parse_data
from app.services.pdf_service import build_watermark


def _identificar_documentos_com_erro():
    com_erro = []
    for documento in Documento2.query.all():
        erros = []
        if documento.vencimento:
            try:
                converter_data(documento.vencimento)
            except ValueError:
                erros.append(f"Data de vencimento inválida: {documento.vencimento}")
        if not documento.organograma:
            erros.append("Organograma não informado")
        if not documento.tipo_documento:
            erros.append("Tipo de documento não informado")
        if not documento.abrangencia:
            erros.append("Abrangência não informada")
        if erros:
            com_erro.append({"documento": documento, "erros": erros})
    return com_erro


def _calcular_status(doc):
    """Retorna dict {status, detalhes, cor, vencimento} baseado no vencimento."""
    try:
        if not doc.vencimento:
            return {
                "status": "Sem data",
                "detalhes": "Sem data de vencimento",
                "cor": "gray",
                "vencimento": "N/A",
            }

        data_vencimento = None
        for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"):
            try:
                data_vencimento = datetime.strptime(doc.vencimento, formato)
                break
            except ValueError:
                continue

        if data_vencimento is None:
            return {
                "status": "Inválido",
                "detalhes": "Formato desconhecido",
                "cor": "darkorange",
                "vencimento": doc.vencimento or "N/A",
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

        dias_vencido = (hoje - data_vencimento).days
        if dias_vencido < 30:
            tempo = f"Há {dias_vencido} dias"
        elif dias_vencido < 365:
            tempo = f"Há {dias_vencido // 30} meses"
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
            "vencimento": doc.vencimento or "N/A",
        }


def _build_pdf_relatorio(documentos, abrangencia, organograma):
    documentos_ordenados = sorted(
        documentos,
        key=lambda doc: (
            (doc.tipo_documento.lower() if doc.tipo_documento else ""),
            not doc.atualizado,
            "Vencido" in _calcular_status(doc)["status"],
        ),
    )

    total = len(documentos_ordenados)
    atualizados = sum(
        1 for doc in documentos_ordenados if _calcular_status(doc)["status"] == "Atualizado"
    )
    desatualizados = total - atualizados

    contagem_por_tipo = {}
    for doc in documentos_ordenados:
        tipo = doc.tipo_documento or "Sem Tipo"
        ct = contagem_por_tipo.setdefault(
            tipo, {"total": 0, "atualizados": 0, "desatualizados": 0}
        )
        ct["total"] += 1
        if _calcular_status(doc)["status"] == "Atualizado":
            ct["atualizados"] += 1
        else:
            ct["desatualizados"] += 1

    buffer = BytesIO()
    pdf_doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()

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
    style_footer = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9,
        textColor=HexColor("#7f8c8d"),
        alignment=TA_CENTER,
        spaceBefore=10,
    )
    style_normal = ParagraphStyle(
        "Normal",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
    )
    style_vencido = ParagraphStyle(
        "Vencido",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=colors.red,
        leading=12,
    )
    style_atualizado = ParagraphStyle(
        "Atualizado",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        textColor=colors.green,
        leading=12,
    )
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

    content = []

    logo_path = os.path.join("static", "logo.png")
    if os.path.exists(logo_path):
        content.append(Image(logo_path, width=120, height=60))
        content.append(Spacer(1, 12))

    content.append(
        Paragraph(
            f"<b>RELATÓRIO DE DOCUMENTOS - {organograma} ({abrangencia})</b>",
            style_title,
        )
    )
    content.append(
        Paragraph(
            f"<b>Data de geração:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            style_normal,
        )
    )
    content.append(Spacer(1, 12))

    # Seção 1: detalhamento por tipo
    content.append(
        Paragraph("<b>DETALHAMENTO POR TIPO DE DOCUMENTO</b>", style_subtitle)
    )

    table_data = [["Nome do Documento", "Status/Vencimento", "Publicação", "Link"]]
    tipo_atual = None
    for documento in documentos_ordenados:
        status_info = _calcular_status(documento)
        if documento.tipo_documento != tipo_atual:
            tipo_atual = documento.tipo_documento
            table_data.append(
                [Paragraph(f"<b>{tipo_atual}</b>", style_header), "", "", ""]
            )

        status_text = f"<b>{status_info['status']}</b><br/>"
        if status_info["status"] in ("Atualizado", "Vencido"):
            status_text += (
                f"{status_info['detalhes']}<br/>({status_info['vencimento']})"
            )
        else:
            status_text += status_info["detalhes"]

        documento_url = f"https://hg.huwc.ufc.br/miac/documento2/{documento.id}"
        link_documento = f'<a href="{documento_url}" color="blue">Abrir</a>'

        text_style = (
            style_vencido
            if status_info["status"] == "Vencido"
            else style_atualizado
            if status_info["status"] == "Atualizado"
            else style_normal
        )

        table_data.append(
            [
                Paragraph(documento.nome, text_style),
                Paragraph(status_text, text_style),
                Paragraph(
                    documento.data_publicacao.split()[0]
                    if documento.data_publicacao
                    else "N/A",
                    text_style,
                ),
                Paragraph(link_documento, text_style),
            ]
        )

    table = Table(table_data, colWidths=[10 * cm, 4 * cm, 2.5 * cm, 2.5 * cm])
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
    for i, row in enumerate(table_data):
        if len(row) > 1 and row[1] == "":
            table_style.add("SPAN", (0, i), (-1, i))
            table_style.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#495057"))
            table_style.add("TEXTCOLOR", (0, i), (-1, i), colors.white)
    table.setStyle(table_style)
    content.append(table)
    content.append(Spacer(1, 16))

    # Seção 2: alertas
    docs_vencidos = [
        doc for doc in documentos_ordenados if _calcular_status(doc)["status"] == "Vencido"
    ]
    docs_proximo_vencer = [
        doc
        for doc in documentos_ordenados
        if _calcular_status(doc)["status"] == "Atualizado"
        and doc.vencimento
        and (parse_data(doc.vencimento) - datetime.now()).days <= 30
    ]
    docs_proximo_vencer.sort(
        key=lambda doc: (parse_data(doc.vencimento) - datetime.now()).days
    )

    if docs_vencidos or docs_proximo_vencer:
        content.append(Paragraph("<b>ALERTAS</b>", style_subtitle))
        alertas_data = [["Tipo", "Documento", "Status", "Vencimento", "Recomendação"]]
        style_tipo = ParagraphStyle(
            "TipoStyle",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=7,
            leading=10,
            wordWrap="LTR",
        )
        style_normal_alerta = ParagraphStyle(
            "NormalAlerta",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            wordWrap="LTR",
        )
        for doc in docs_vencidos:
            status = _calcular_status(doc)
            alertas_data.append(
                [
                    Paragraph(doc.tipo_documento or "Sem Tipo", style_tipo),
                    Paragraph(doc.nome, style_normal_alerta),
                    "Vencido",
                    status["vencimento"],
                    "Revisão Imediata",
                ]
            )
        for doc in docs_proximo_vencer:
            status = _calcular_status(doc)
            dias_restantes = (parse_data(doc.vencimento) - datetime.now()).days
            alertas_data.append(
                [
                    Paragraph(doc.tipo_documento or "Sem Tipo", style_tipo),
                    Paragraph(doc.nome, style_normal_alerta),
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
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
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
                    ("WORDWRAP", (1, 1), (1, -1), True),
                    ("LEADING", (0, 1), (-1, -1), 12),
                    ("TOPPADDING", (0, 1), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
                ]
            )
        )
        content.append(alertas_table)
        content.append(Spacer(1, 16))

    # Seção 3: resumo
    content.append(Paragraph("<b>RESUMO ESTATÍSTICO</b>", style_subtitle))
    resumo_data = [
        ["RELATÓRIO DE DOCUMENTOS", "TOTAL", "ATUALIZADOS", "DESATUALIZADOS"],
        [
            Paragraph("<b>TOTAL GERAL</b>", style_normal),
            str(total),
            Paragraph(
                f"<font color=green>{atualizados}</font> "
                f"({atualizados/total*100:.1f}%)",
                style_normal,
            ),
            Paragraph(
                f"<font color=red>{desatualizados}</font> "
                f"({desatualizados/total*100:.1f}%)",
                style_normal,
            ),
        ],
        ["", "", "", ""],
    ]
    for tipo, dados in sorted(contagem_por_tipo.items()):
        resumo_data.append(
            [
                tipo,
                str(dados["total"]),
                Paragraph(
                    f"<font color=green>{dados['atualizados']}</font> "
                    f"({dados['atualizados']/dados['total']*100:.1f}%)",
                    style_normal,
                ),
                Paragraph(
                    f"<font color=red>{dados['desatualizados']}</font> "
                    f"({dados['desatualizados']/dados['total']*100:.1f}%)",
                    style_normal,
                ),
            ]
        )
    resumo_table = Table(resumo_data, colWidths=[8 * cm, 2.5 * cm, 4 * cm, 4 * cm])
    resumo_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#2c3e50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("BACKGROUND", (0, 1), (-1, 1), HexColor("#e8f4fc")),
                ("LINEBELOW", (0, 1), (-1, 1), 1, colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dee2e6")),
                ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, HexColor("#f8f9fa")]),
            ]
        )
    )
    content.append(resumo_table)
    content.append(Spacer(1, 16))

    # QR Code + rodapé
    relatorio_url = (
        f"https://hg.huwc.ufc.br/miac/gerar_relatorio/{abrangencia}/{organograma}"
    )
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

    watermark = build_watermark(OrganizacaoConfig.get().logo_path)
    pdf_doc.build(content, onFirstPage=watermark, onLaterPages=watermark)
    buffer.seek(0)
    return buffer


def init_routes(app):
    @app.route("/miac/gerar_relatorio/<abrangencia>/<organograma>")
    def gerar_relatorio(abrangencia, organograma):
        try:
            documentos = Documento2.query.filter_by(
                organograma=organograma, abrangencia=abrangencia
            ).all()
            if not documentos:
                return (
                    "Nenhum documento encontrado para os critérios especificados",
                    404,
                )

            buffer = _build_pdf_relatorio(documentos, abrangencia, organograma)
            return send_file(
                buffer,
                as_attachment=True,
                download_name=(
                    f"Relatorio_{organograma}_{abrangencia}"
                    f"_{datetime.now().strftime('%Y%m%d')}.pdf"
                ),
                mimetype="application/pdf",
            )
        except Exception as exc:
            logger.exception("Erro ao gerar relatório PDF")
            return f"Erro ao gerar relatório: {exc}", 500

    @app.route("/miac/estatisticas", methods=["GET"])
    def estatisticas():
        if "username" not in session:
            return redirect(url_for("login"))

        abrangencia_filtro = request.args.get("abrangencia", "").strip()
        organograma_filtro = request.args.get("organograma", "").strip()
        tipo_documento_filtro = request.args.get("tipo_documento", "").strip()
        status_filtro = request.args.get("status", "").strip()

        query = Documento2.query
        if abrangencia_filtro:
            query = query.filter(Documento2.abrangencia == abrangencia_filtro)
        if organograma_filtro:
            query = query.filter(Documento2.organograma == organograma_filtro)
        if tipo_documento_filtro:
            query = query.filter(Documento2.tipo_documento == tipo_documento_filtro)
        if status_filtro == "atualizado":
            query = query.filter(Documento2.atualizado.is_(True))
        elif status_filtro == "desatualizado":
            query = query.filter(Documento2.atualizado.is_(False))

        documentos = query.all()
        stats = {
            "total": len(documentos),
            "atualizados": sum(1 for doc in documentos if doc.atualizado),
            "desatualizados": sum(1 for doc in documentos if not doc.atualizado),
            "por_tipo": {},
            "por_abrangencia": {},
            "por_organograma": {},
            "por_marcador": {},
        }

        agregacoes = [
            ("por_tipo", lambda d: d.tipo_documento),
            ("por_abrangencia", lambda d: d.abrangencia),
            ("por_organograma", lambda d: d.organograma),
            ("por_marcador", lambda d: d.marcador or "Sem Marcador"),
        ]
        for doc in documentos:
            for chave, extractor in agregacoes:
                valor = extractor(doc)
                bucket = stats[chave].setdefault(
                    valor, {"total": 0, "atualizados": 0, "desatualizados": 0}
                )
                bucket["total"] += 1
                if doc.atualizado:
                    bucket["atualizados"] += 1
                else:
                    bucket["desatualizados"] += 1

        notificacoes = []
        for doc in Documento2.query.filter(Documento2.vencimento.isnot(None)).all():
            try:
                data_venc = parse_data(doc.vencimento).date()
                dias = (data_venc - datetime.now().date()).days
                if 0 <= dias <= 30:
                    notificacoes.append(
                        f"Documento '{doc.nome}' vence em {dias} dias."
                    )
                elif dias < 0:
                    notificacoes.append(
                        f"Documento '{doc.nome}' está vencido há {-dias} dias."
                    )
            except ValueError:
                continue

        documentos_com_erro = _identificar_documentos_com_erro()

        return render_template(
            "estatisticas.html",
            stats=stats,
            notificacoes=notificacoes,
            documentos_com_erro=documentos_com_erro,
            abrangencias=Documento2.query.with_entities(
                Documento2.abrangencia
            ).distinct(),
            organogramas=Documento2.query.with_entities(
                Documento2.organograma
            ).distinct(),
            tipos_documento=Documento2.query.with_entities(
                Documento2.tipo_documento
            ).distinct(),
        )
