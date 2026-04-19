"""Serviços de manipulação de PDF: extração de texto e marca d'água em relatórios."""
import os
import re

import fitz
from reportlab.lib.pagesizes import letter


def clean_text(text):
    """Colapsa whitespace em um espaço único."""
    return re.sub(r"\s+", " ", text).strip()


def read_last_page(file_path):
    """Extrai texto apenas da última página do PDF; retorna None em caso de erro."""
    doc = None
    try:
        doc = fitz.open(file_path)
        page = doc.load_page(-1)
        text = page.get_text("text")
        cleaned = clean_text(text)
        return cleaned if cleaned.strip() else None
    except Exception as exc:
        print(f"Erro crítico ao ler PDF {file_path}: {exc}")
        return None
    finally:
        if doc is not None:
            doc.close()


def add_watermark(canvas, _doc):
    """Callback usado em SimpleDocTemplate.build para desenhar marca d'água."""
    canvas.saveState()

    marca_fundo_path = os.path.join("static", "marca_fundo.png")
    if os.path.exists(marca_fundo_path):
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
    else:
        print(f"Erro: A imagem {marca_fundo_path} não foi encontrada.")

    marca_cabecalho_path = os.path.join("static", "marca_cabecalho.png")
    if os.path.exists(marca_cabecalho_path):
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
    else:
        print(f"Erro: A imagem {marca_cabecalho_path} não foi encontrada.")

    canvas.restoreState()
