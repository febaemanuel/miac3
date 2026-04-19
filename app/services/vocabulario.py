"""Resolve valores retornados pela IA contra tabelas de vocabulário controlado."""
from app.models import (
    Abrangencia,
    AbrangenciaSinonimo,
    Organograma,
    TipoDocumento,
)


def _invalido(valor):
    return not valor or valor == "Não localizado"


def resolver_abrangencia(valor):
    if _invalido(valor):
        return None
    if Abrangencia.query.filter_by(nome=valor, ativo=True).first():
        return valor
    sinonimo = AbrangenciaSinonimo.query.filter_by(de=valor).first()
    return sinonimo.para.nome if sinonimo else None


def resolver_organograma(valor):
    if _invalido(valor):
        return None
    if Organograma.query.filter_by(nome=valor).first():
        return valor
    return None


def resolver_tipo_documento(valor):
    if _invalido(valor):
        return None
    if TipoDocumento.query.filter_by(nome=valor).first():
        return valor
    return None


def listar_abrangencias():
    return [a.nome for a in Abrangencia.query.filter_by(ativo=True).order_by(Abrangencia.nome)]


def listar_organogramas():
    return [o.nome for o in Organograma.query.order_by(Organograma.nome)]


def listar_tipos_documento():
    return [t.nome for t in TipoDocumento.query.order_by(TipoDocumento.nome)]
