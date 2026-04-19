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

from app.extensions import db
from app.models import Documento2

logger = logging.getLogger(__name__)

DATE_FORMATS = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"]


def parse_data(data_str):
    """Parses a date string using supported formats."""
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(data_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Formato de data inválido: {data_str}")


def calcular_status(doc):
    """Returns dict with status, details, color and formatted expiry for a document."""
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


def converter_data(data):
    """Returns date object from string."""
    return parse_data(data).date()


def formatar_data_para_input(data_str):
    """Converts date to yyyy-mm-dd format for HTML date input."""
    if not data_str:
        return ""
    try:
        return parse_data(data_str).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def verificar_vencimentos():
    """Returns list of notifications about expired or expiring documents."""
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
    """Identifies documents with validation errors."""
    documentos_com_erro = []
    documentos = Documento2.query.all()

    for documento in documentos:
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
            documentos_com_erro.append({"documento": documento, "erros": erros})

    return documentos_com_erro


def atualizar_status_documentos():
    """Updates the 'atualizado' field for all documents based on expiry date."""
    documentos = Documento2.query.all()
    for documento in documentos:
        if documento.vencimento:
            try:
                data_vencimento = converter_data(documento.vencimento)
                documento.atualizado = data_vencimento >= datetime.now().date()
            except ValueError as e:
                logger.warning("Erro ao converter data do documento %d: %s", documento.id, e)

    db.session.commit()


def normalizar_texto(texto):
    """Removes accents and converts to lowercase."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    return texto.lower()


def clean_text(text):
    """Removes bad characters and normalizes whitespace."""
    return re.sub(r"\s+", " ", text).strip()


def read_last_page(file_path):
    """Extracts text from the last page of a PDF."""
    try:
        doc = fitz.open(file_path)
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


def send_to_deepseek_with_retry(prompt, api_key, retries=3, delay=2):
    """Sends prompt to DeepSeek API with retry logic."""
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
    """Sends prompt to OpenAI GPT API with retry logic."""
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


def add_watermark(canvas, doc):
    """Adds watermark images to PDF pages."""
    canvas.saveState()

    marca_fundo_path = os.path.join("static", "marca_fundo.png")
    if os.path.exists(marca_fundo_path):
        canvas.setFillAlpha(0.05)
        canvas.drawImage(
            marca_fundo_path, x=0, y=200,
            width=letter[0], height=letter[1] * 0.75,
            preserveAspectRatio=True, mask="auto",
        )

    marca_cabecalho_path = os.path.join("static", "marca_cabecalho.png")
    if os.path.exists(marca_cabecalho_path):
        canvas.setFillAlpha(1.0)
        canvas.drawImage(
            marca_cabecalho_path, x=200, y=720,
            width=400, height=100,
            preserveAspectRatio=True, mask="auto",
        )

    canvas.restoreState()


def expired_duration(vencimento):
    """Template filter: formats duration since document expired."""
    try:
        exp_date = datetime.strptime(vencimento, "%d/%m/%Y")
    except ValueError:
        try:
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
