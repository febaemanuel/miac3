"""Fixtures pytest: app isolado em SQLite memória com dados mínimos."""
import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test")

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.config import Config
from app.extensions import db
from app.models import Abrangencia, AbrangenciaSinonimo, Usuario
from app.seed import _seed_filtros_publicados


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


@pytest.fixture
def app():
    flask_app = create_app(TestConfig)
    with flask_app.app_context():
        db.drop_all()
        db.create_all()
        unidade_a = Abrangencia(nome="UNIDADE_A", ativo=True)
        unidade_b = Abrangencia(nome="UNIDADE_B", ativo=True)
        db.session.add_all([unidade_a, unidade_b])
        db.session.flush()
        db.session.add(AbrangenciaSinonimo(de="SINONIMO_A", para_id=unidade_a.id))
        db.session.add(Usuario(
            username="teste",
            senha_hash=generate_password_hash("senha123"),
            nivel_acesso="elevado",
            ativo=True,
        ))
        _seed_filtros_publicados()
        db.session.commit()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logged_client(client):
    client.post("/miac/login", data={"username": "teste", "password": "senha123"})
    return client
