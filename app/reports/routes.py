"""Report generation and statistics routes."""
import logging
import os
from datetime import datetime
from io import BytesIO

import qrcode
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, send_file,
)
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, Image,
)

from flask import current_app
from app.decorators import login_required
from app.extensions import db
from app.helpers import aplicar_filtros_query
from app.models import Documento2
from app.utils import (
    calcular_status, parse_data, add_watermark,
    verificar_vencimentos, identificar_documentos_com_erro,
)

reports_bp = Blueprint("reports", __name__, url_prefix="/miac")
logger = logging.getLogger(__name__)


@reports_bp.route("/estatisticas", methods=["GET"])
@login_required
def estatisticas():
    abrangencia_filtro = request.args.get("abrangencia", "").strip()
    organograma_filtro = request.args.get("organograma", "").strip()
    tipo_documento_filtro = request.args.get("tipo_documento", "").strip()
    status_filtro = request.args.get("status", "").strip()

    query = Documento2.query
    query = aplicar_filtros_query(
        query,
        abrangencia=abrangencia_filtro,
        organograma=organograma_filtro,
        tipo_documento=tipo_documento_filtro,
        status=status_filtro,
    )

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

    for doc in documentos:
        # Group by tipo_documento
        if doc.tipo_documento not in stats["por_tipo"]:
            stats["por_tipo"][doc.tipo_documento] = {"total": 0, "atualizados": 0, "desatualizados": 0}
        stats["por_tipo"][doc.tipo_documento]["total"] += 1
        if doc.atualizado:
            stats["por_tipo"][doc.tipo_documento]["atualizados"] += 1
        else:
            stats["por_tipo"][doc.tipo_documento]["desatualizados"] += 1

        # Group by abrangencia
        if doc.abrangencia not in stats["por_abrangencia"]:
            stats["por_abrangencia"][doc.abrangencia] = {"total": 0, "atualizados": 0, "desatualizados": 0}
        stats["por_abrangencia"][doc.abrangencia]["total"] += 1
        if doc.atualizado:
            stats["por_abrangencia"][doc.abrangencia]["atualizados"] += 1
        else:
            stats["por_abrangencia"][doc.abrangencia]["desatualizados"] += 1

        # Group by organograma
        if doc.organograma not in stats["por_organograma"]:
            stats["por_organograma"][doc.organograma] = {"total": 0, "atualizados": 0, "desatualizados": 0}
        stats["por_organograma"][doc.organograma]["total"] += 1
        if doc.atualizado:
            stats["por_organograma"][doc.organograma]["atualizados"] += 1
        else:
            stats["por_organograma"][doc.organograma]["desatualizados"] += 1

        # Group by marcador
        marcador = doc.marcador if doc.marcador else "Sem Marcador"
        if marcador not in stats["por_marcador"]:
            stats["por_marcador"][marcador] = {"total": 0, "atualizados": 0, "desatualizados": 0}
        stats["por_marcador"][marcador]["total"] += 1
        if doc.atualizado:
            stats["por_marcador"][marcador]["atualizados"] += 1
        else:
            stats["por_marcador"][marcador]["desatualizados"] += 1

    notificacoes = verificar_vencimentos()
    documentos_com_erro = identificar_documentos_com_erro()

    return render_template(
        "estatisticas.html",
        stats=stats,
        notificacoes=notificacoes,
        documentos_com_erro=documentos_com_erro,
        abrangencias=Documento2.query.with_entities(Documento2.abrangencia).distinct(),
        organogramas=Documento2.query.with_entities(Documento2.organograma).distinct(),
        tipos_documento=Documento2.query.with_entities(Documento2.tipo_documento).distinct(),
    )


@reports_bp.route("/gerar_relatorio/<abrangencia>/<organograma>")
@login_required
def gerar_relatorio(abrangencia, organograma):
    try:
        documentos = Documento2.query.filter_by(
            organograma=organograma, abrangencia=abrangencia
        ).all()

        if not documentos:
            return "Nenhum documento encontrado para os critérios especificados", 404

        # Sort: by tipo (A-Z), then updated first
        documentos_ordenados = sorted(
            documentos,
            key=lambda doc: (
                (doc.tipo_documento.lower() if doc.tipo_documento else ""),
                not doc.atualizado,
                "Vencido" in calcular_status(doc)["status"],
            ),
        )

        total = len(documentos_ordenados)
        atualizados = sum(
            1 for doc in documentos_ordenados
            if calcular_status(doc)["status"] == "Atualizado"
        )
        desatualizados = total - atualizados

        contagem_por_tipo = {}
        for doc in documentos_ordenados:
            tipo = doc.tipo_documento if doc.tipo_documento else "Sem Tipo"
            if tipo not in contagem_por_tipo:
                contagem_por_tipo[tipo] = {"total": 0, "atualizados": 0, "desatualizados": 0}
            contagem_por_tipo[tipo]["total"] += 1
            if calcular_status(doc)["status"] == "Atualizado":
                contagem_por_tipo[tipo]["atualizados"] += 1
            else:
                contagem_por_tipo[tipo]["desatualizados"] += 1

        buffer = BytesIO()

        pdf_doc = SimpleDocTemplate(
            buffer, pagesize=letter,
            leftMargin=1.5 * cm, rightMargin=1.5 * cm,
            topMargin=2 * cm, bottomMargin=2 * cm,
        )

        styles = getSampleStyleSheet()

        style_title = ParagraphStyle(
            "ReportTitle", parent=styles["Title"],
            fontName="Helvetica-Bold", fontSize=16,
            textColor=HexColor("#2c3e50"), leading=20,
            alignment=TA_CENTER, spaceAfter=12,
        )
        style_header = ParagraphStyle(
            "ReportHeader", parent=styles["Normal"],
            fontName="Helvetica-Bold", fontSize=10,
            textColor=HexColor("#ffffff"), leading=12,
            alignment=TA_CENTER, backColor=HexColor("#2c3e50"),
        )
        style_footer = ParagraphStyle(
            "ReportFooter", parent=styles["Normal"],
            fontName="Helvetica-Oblique", fontSize=9,
            textColor=HexColor("#7f8c8d"), alignment=TA_CENTER,
            spaceBefore=10,
        )
        style_normal = ParagraphStyle(
            "ReportNormal", parent=styles["BodyText"],
            fontName="Helvetica", fontSize=9, leading=12,
        )
        style_vencido = ParagraphStyle(
            "ReportVencido", parent=styles["BodyText"],
            fontName="Helvetica-Bold", fontSize=9,
            textColor=colors.red, leading=12,
        )
        style_atualizado = ParagraphStyle(
            "ReportAtualizado", parent=styles["BodyText"],
            fontName="Helvetica", fontSize=9,
            textColor=colors.green, leading=12,
        )
        style_subtitle = ParagraphStyle(
            "ReportSubtitle", parent=styles["Heading2"],
            fontName="Helvetica-Bold", fontSize=12,
            textColor=HexColor("#3498db"), leading=14,
            spaceBefore=10, spaceAfter=6,
        )

        content = []

        # Logo
        logo_path = os.path.join("static", "logo.png")
        if os.path.exists(logo_path):
            logo = Image(logo_path, width=120, height=60)
            content.append(logo)
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

        # Section 1: Document detail table
        content.append(
            Paragraph("<b>DETALHAMENTO POR TIPO DE DOCUMENTO</b>", style_subtitle)
        )

        table_data = [["Nome do Documento", "Status/Vencimento", "Publicação", "Link"]]

        base_url = current_app.config["BASE_URL"]
        tipo_atual = None
        for documento in documentos_ordenados:
            status_info = calcular_status(documento)

            if documento.tipo_documento != tipo_atual:
                tipo_atual = documento.tipo_documento
                table_data.append(
                    [Paragraph(f"<b>{tipo_atual}</b>", style_header), "", "", ""]
                )

            status_text = f"<b>{status_info['status']}</b><br/>"
            if status_info["status"] in ["Atualizado", "Vencido"]:
                status_text += f"{status_info['detalhes']}<br/>({status_info['vencimento']})"
            else:
                status_text += status_info["detalhes"]

            documento_url = f"{base_url}/miac/documento2/{documento.id}"
            link_documento = f'<a href="{documento_url}" color="blue">Abrir</a>'

            text_style = (
                style_vencido if status_info["status"] == "Vencido"
                else (style_atualizado if status_info["status"] == "Atualizado" else style_normal)
            )

            table_data.append([
                Paragraph(documento.nome, text_style),
                Paragraph(status_text, text_style),
                Paragraph(
                    documento.data_publicacao.split()[0] if documento.data_publicacao else "N/A",
                    text_style,
                ),
                Paragraph(link_documento, text_style),
            ])

        table = Table(table_data, colWidths=[10 * cm, 4 * cm, 2.5 * cm, 2.5 * cm])

        table_style = TableStyle([
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
        ])

        for i, row in enumerate(table_data):
            if len(row) > 1 and row[1] == "":
                table_style.add("SPAN", (0, i), (-1, i))
                table_style.add("BACKGROUND", (0, i), (-1, i), colors.HexColor("#495057"))
                table_style.add("TEXTCOLOR", (0, i), (-1, i), colors.white)

        table.setStyle(table_style)
        content.append(table)
        content.append(Spacer(1, 16))

        # Section 2: Alerts
        docs_vencidos = [
            doc for doc in documentos_ordenados
            if calcular_status(doc)["status"] == "Vencido"
        ]
        docs_proximo_vencer = [
            doc for doc in documentos_ordenados
            if calcular_status(doc)["status"] == "Atualizado"
            and doc.vencimento
            and (parse_data(doc.vencimento) - datetime.now()).days <= 30
        ]
        docs_proximo_vencer.sort(
            key=lambda doc: (parse_data(doc.vencimento) - datetime.now()).days
        )

        if docs_vencidos or docs_proximo_vencer:
            content.append(Paragraph("<b>ALERTAS</b>", style_subtitle))

            alertas_data = [["Tipo", "Documento", "Status", "Vencimento", "Recomendação"]]

            style_normal_wrap = ParagraphStyle(
                "NormalWrap", parent=styles["BodyText"],
                fontName="Helvetica", fontSize=9, leading=12, wordWrap="LTR",
            )
            style_tipo = ParagraphStyle(
                "TipoStyle", parent=styles["BodyText"],
                fontName="Helvetica", fontSize=7, leading=10, wordWrap="LTR",
            )

            for doc in docs_vencidos:
                status = calcular_status(doc)
                alertas_data.append([
                    Paragraph(doc.tipo_documento or "Sem Tipo", style_tipo),
                    Paragraph(doc.nome, style_normal_wrap),
                    "Vencido",
                    status["vencimento"],
                    "Revisão Imediata",
                ])

            for doc in docs_proximo_vencer:
                status = calcular_status(doc)
                dias_restantes = (parse_data(doc.vencimento) - datetime.now()).days
                alertas_data.append([
                    Paragraph(doc.tipo_documento or "Sem Tipo", style_tipo),
                    Paragraph(doc.nome, style_normal_wrap),
                    f"Vence em {dias_restantes} dias",
                    status["vencimento"],
                    "Planejar Revisão",
                ])

            alertas_table = Table(
                alertas_data, colWidths=[3 * cm, 7 * cm, 3 * cm, 3 * cm, 3 * cm]
            )
            alertas_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#b22222")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8f9fa")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
                ("TEXTCOLOR", (0, 1), (-1, -1), colors.black),
                ("TEXTCOLOR", (2, 1), (2, -1), colors.red),
                ("WORDWRAP", (1, 1), (1, -1), True),
                ("LEADING", (0, 1), (-1, -1), 12),
                ("TOPPADDING", (0, 1), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ]))

            content.append(alertas_table)
            content.append(Spacer(1, 16))

        # Section 3: Statistical summary
        content.append(Paragraph("<b>RESUMO ESTATÍSTICO</b>", style_subtitle))

        resumo_data = [
            ["RELATÓRIO DE DOCUMENTOS", "TOTAL", "ATUALIZADOS", "DESATUALIZADOS"],
            [
                Paragraph("<b>TOTAL GERAL</b>", style_normal),
                str(total),
                Paragraph(f"<font color=green>{atualizados}</font> ({atualizados/total*100:.1f}%)", style_normal),
                Paragraph(f"<font color=red>{desatualizados}</font> ({desatualizados/total*100:.1f}%)", style_normal),
            ],
            ["", "", "", ""],
        ]

        for tipo, dados in sorted(contagem_por_tipo.items()):
            resumo_data.append([
                tipo,
                str(dados["total"]),
                Paragraph(f"<font color=green>{dados['atualizados']}</font> ({dados['atualizados']/dados['total']*100:.1f}%)", style_normal),
                Paragraph(f"<font color=red>{dados['desatualizados']}</font> ({dados['desatualizados']/dados['total']*100:.1f}%)", style_normal),
            ])

        resumo_table = Table(resumo_data, colWidths=[8 * cm, 2.5 * cm, 4 * cm, 4 * cm])
        resumo_table.setStyle(TableStyle([
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
        ]))

        content.append(resumo_table)
        content.append(Spacer(1, 16))

        # QR Code footer
        relatorio_url = f"{base_url}/miac/gerar_relatorio/{abrangencia}/{organograma}"

        qr = qrcode.QRCode(
            version=1, error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=3, border=2,
        )
        qr.add_data(relatorio_url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_img_buffer = BytesIO()
        qr_img.save(qr_img_buffer, format="PNG")
        qr_img_buffer.seek(0)

        footer_table = Table(
            [[
                Image(qr_img_buffer, width=80, height=80),
                Paragraph(
                    "<b>Módulo Integrado de Arquivos e Controle</b><br/>"
                    "Sistema de Gestão Documental - UGQ<br/>"
                    f"Relatório gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}<br/>"
                    "Escaneie o código ao lado para acessar a versão online",
                    style_footer,
                ),
            ]],
            colWidths=[4 * cm, 12 * cm],
        )
        footer_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
        ]))

        content.append(footer_table)

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
