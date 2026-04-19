"""Testes do resolver de vocabulário controlado."""
from app.services.vocabulario import (
    resolver_abrangencia,
    resolver_organograma,
    resolver_tipo_documento,
)


def test_abrangencia_match_exato(app):
    with app.app_context():
        assert resolver_abrangencia("HUWC") == "HUWC"


def test_abrangencia_via_sinonimo(app):
    with app.app_context():
        assert resolver_abrangencia("CHUFC") == "HUWC"


def test_abrangencia_invalida_retorna_none(app):
    with app.app_context():
        assert resolver_abrangencia("XYZ") is None


def test_abrangencia_nao_localizado_retorna_none(app):
    with app.app_context():
        assert resolver_abrangencia("Não localizado") is None
        assert resolver_abrangencia("") is None
        assert resolver_abrangencia(None) is None


def test_organograma_sem_match_retorna_none(app):
    with app.app_context():
        assert resolver_organograma("QUALQUER") is None


def test_tipo_documento_sem_match_retorna_none(app):
    with app.app_context():
        assert resolver_tipo_documento("FORMULARIO") is None
