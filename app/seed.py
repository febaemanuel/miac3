"""Povoamento inicial de usuários e singletons de configuração."""
import os

from werkzeug.security import generate_password_hash

from sqlalchemy import text

from app.extensions import db
from app.models import IaConfig, OrganizacaoConfig, Usuario


def _enable_extensions():
    if db.engine.dialect.name != "postgresql":
        return
    db.session.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))


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
    _enable_extensions()
    _seed_usuarios()
    OrganizacaoConfig.get()
    IaConfig.get()
    db.session.commit()
