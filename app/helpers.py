"""Shared helper functions used across blueprints."""
from datetime import datetime

from app.extensions import db
from app.models import Documento2
from app.utils import parse_data


def get_organogramas_formatados():
    """Returns list of dicts {sigla, nome_completo} sorted by name."""
    rows = (
        db.session.query(Documento2.organograma, Documento2.nome_completo)
        .distinct()
        .all()
    )
    result = [{"sigla": r[0], "nome_completo": r[1]} for r in rows]
    result.sort(key=lambda x: (x["nome_completo"] or x["sigla"] or "").lower())
    return result


def calcular_stats_dashboard(abrangencia=None):
    """Returns dict with quick document statistics."""
    query = Documento2.query
    if abrangencia:
        query = query.filter_by(abrangencia=abrangencia)
    docs = query.all()
    total = len(docs)
    atualizados = sum(1 for d in docs if d.atualizado)
    vencidos = total - atualizados
    hoje = datetime.now()
    proximos = 0
    for d in docs:
        if d.atualizado and d.vencimento:
            try:
                dt = parse_data(d.vencimento)
                if 0 <= (dt - hoje).days <= 30:
                    proximos += 1
            except ValueError:
                pass
    return {
        "total": total,
        "atualizados": atualizados,
        "vencidos": vencidos,
        "proximos_vencer": proximos,
        "pct_atualizado": round(atualizados / total * 100) if total else 0,
    }


def agrupar_documentos(documentos):
    """Groups Documento2 list into {marcador: {organograma: {tipo: [docs]}}}."""
    agrupados = {}
    for doc in documentos:
        marcador = doc.marcador or "Sem Marcador"
        agrupados.setdefault(marcador, {})
        agrupados[marcador].setdefault(doc.organograma, {})
        agrupados[marcador][doc.organograma].setdefault(doc.tipo_documento, [])
        agrupados[marcador][doc.organograma][doc.tipo_documento].append(doc)
    return agrupados


def aplicar_filtros_query(query, abrangencia=None, organograma=None,
                          tipo_documento=None, status=None):
    """Applies common filters to a Documento2 query."""
    if abrangencia:
        query = query.filter(Documento2.abrangencia == abrangencia)
    if organograma:
        query = query.filter(Documento2.organograma == organograma)
    if tipo_documento:
        query = query.filter(Documento2.tipo_documento == tipo_documento)
    if status == "atualizado":
        query = query.filter(Documento2.atualizado == True)
    elif status in ("desatualizado", "vencido"):
        query = query.filter(Documento2.atualizado == False)
    return query
