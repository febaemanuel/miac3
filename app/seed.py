"""Povoamento inicial de tabelas de vocabulário e usuários."""
import os

from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import (
    Abrangencia,
    AbrangenciaSinonimo,
    Documento2,
    Organograma,
    TipoDocumento,
    Usuario,
)


SINONIMOS_EBSERH = {"CHUFC": "HUWC", "CH": "HUWC"}


def _seed_abrangencias():
    existentes = {a.nome for a in Abrangencia.query.all()}
    for (nome,) in db.session.query(Documento2.abrangencia).distinct():
        if nome and nome not in existentes:
            db.session.add(Abrangencia(nome=nome))
            existentes.add(nome)
    db.session.flush()

    for de, para in SINONIMOS_EBSERH.items():
        alvo = Abrangencia.query.filter_by(nome=para).first()
        if not alvo:
            continue
        if not AbrangenciaSinonimo.query.filter_by(de=de).first():
            db.session.add(AbrangenciaSinonimo(de=de, para_id=alvo.id))


def _seed_organogramas():
    existentes = {o.nome for o in Organograma.query.all()}
    for (nome,) in db.session.query(Documento2.organograma).distinct():
        if nome and nome not in existentes:
            db.session.add(Organograma(nome=nome))
            existentes.add(nome)


def _seed_tipos_documento():
    existentes = {t.nome for t in TipoDocumento.query.all()}
    for (nome,) in db.session.query(Documento2.tipo_documento).distinct():
        if nome and nome not in existentes:
            db.session.add(TipoDocumento(nome=nome))
            existentes.add(nome)


def _seed_usuarios():
    if Usuario.query.first():
        return

    padrao_user = os.environ.get("USER_PADRAO_USERNAME")
    padrao_hash = os.environ.get("USER_PADRAO_HASH")
    admin_user = os.environ.get("USER_ADMIN_USERNAME")
    admin_hash = os.environ.get("USER_ADMIN_HASH")

    if padrao_user and padrao_hash:
        db.session.add(Usuario(
            username=padrao_user, senha_hash=padrao_hash, nivel_acesso="padrao"
        ))
    if admin_user and admin_hash:
        db.session.add(Usuario(
            username=admin_user, senha_hash=admin_hash, nivel_acesso="elevado"
        ))

    if not Usuario.query.first() and not (padrao_user or admin_user):
        db.session.add(Usuario(
            username="admin",
            senha_hash=generate_password_hash("admin"),
            nivel_acesso="elevado",
        ))


def run_seeds():
    _seed_abrangencias()
    _seed_organogramas()
    _seed_tipos_documento()
    _seed_usuarios()
    db.session.commit()
