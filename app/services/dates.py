"""Utilidades de parsing/formatação de datas e normalização de texto."""
import unicodedata
from datetime import datetime


def parse_data(data_str):
    """Converte string em datetime tentando vários formatos comuns."""
    formatos = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"]
    for fmt in formatos:
        try:
            return datetime.strptime(data_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Formato de data inválido: {data_str}")


def converter_data(data):
    """Converte string em date. Usado para comparar contra datetime.now().date()."""
    formatos = ["%Y-%m-%d", "%d/%m/%Y"]
    for formato in formatos:
        try:
            return datetime.strptime(data, formato).date()
        except ValueError:
            continue
    raise ValueError(f"Formato de data inválido: {data}")


def formatar_data_para_input(data_str):
    """Converte datas para yyyy-mm-dd (formato de <input type='date'>)."""
    if not data_str:
        return ""
    try:
        if "/" in data_str:
            return datetime.strptime(data_str, "%d/%m/%Y").strftime("%Y-%m-%d")
        if "-" in data_str:
            return data_str.split()[0]
    except ValueError:
        return ""
    return data_str


def normalizar_texto(texto):
    """Remove acentos e converte para minúsculas (usado em buscas ilike+unaccent)."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    return texto.lower()


def expired_duration_filter(vencimento):
    """Template filter: quanto tempo um documento está vencido."""
    try:
        exp_date = datetime.strptime(vencimento, "%d/%m/%Y")
    except ValueError:
        try:
            exp_date = datetime.strptime(vencimento, "%Y-%m-%d")
        except Exception:
            return ""
    days = (datetime.now() - exp_date).days
    if days < 30:
        return f"{days} dia{'s' if days != 1 else ''}"
    if days < 365:
        months = days // 30
        return f"{months} mês{'es' if months != 1 else ''}"
    years = days // 365
    return f"{years} ano{'s' if years != 1 else ''}"
