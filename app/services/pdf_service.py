"""Serviços de manipulação de PDF: extração de texto e marca d'água em relatórios."""
import logging
import os
import re

import fitz
from reportlab.lib.pagesizes import letter

logger = logging.getLogger(__name__)


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
    except Exception:
        logger.exception("Erro crítico ao ler PDF %s", file_path)
        return None
    finally:
        if doc is not None:
            doc.close()


def build_watermark(logo_path=None):
    """Factory: devolve callback de marca d'água; usa `logo_path` se existir, senão marca_cabecalho.png."""
    marca_fundo_path = os.path.join("static", "marca_fundo.png")
    cabecalho_path = (
        os.path.join("static", logo_path)
        if logo_path and os.path.exists(os.path.join("static", logo_path))
        else os.path.join("static", "marca_cabecalho.png")
    )

    def _draw(canvas, _doc):
        canvas.saveState()
        if os.path.exists(marca_fundo_path):
            canvas.setFillAlpha(0.05)
            canvas.drawImage(
                marca_fundo_path,
                x=0, y=200,
                width=letter[0], height=letter[1] * 0.75,
                preserveAspectRatio=True, mask="auto",
            )
        else:
            logger.warning("Marca d'água de fundo ausente: %s", marca_fundo_path)

        if os.path.exists(cabecalho_path):
            canvas.setFillAlpha(1.0)
            canvas.drawImage(
                cabecalho_path,
                x=200, y=720,
                width=400, height=100,
                preserveAspectRatio=True, mask="auto",
            )
        else:
            logger.warning("Logo/cabeçalho do PDF ausente: %s", cabecalho_path)

        canvas.restoreState()

    return _draw


# Mantém compatibilidade: versão padrão sem logo customizado
add_watermark = build_watermark()
