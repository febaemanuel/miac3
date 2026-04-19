"""Modelos SQLAlchemy."""
from sqlalchemy import JSON
from sqlalchemy.ext.mutable import MutableList

from app.extensions import db


class Documento(db.Model):
    """Documento do fluxo manual antigo. Mantido para não quebrar registros legados."""

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(400))
    caminho = db.Column(db.String(200))
    data_publicacao = db.Column(db.String(50))
    data_elaboracao = db.Column(db.String(50))
    vencimento = db.Column(db.String(50), nullable=True)
    numero_sei = db.Column(db.String(50), nullable=True)
    elaboradores = db.Column(db.String(200), nullable=True)
    organograma = db.Column(db.String(100), nullable=True)
    tipo_documento = db.Column(db.String(100), nullable=True)
    abrangencia = db.Column(db.String(50), nullable=True)
    atualizado = db.Column(db.Boolean, nullable=True)


class Documento2(db.Model):
    """Documento do fluxo IA, com versionamento."""

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(400))
    organograma = db.Column(db.String(100))
    tipo_documento = db.Column(db.String(100))
    caminho = db.Column(db.String(200))
    pdf_antigo = db.Column(db.String(200), nullable=True)
    data_publicacao = db.Column(db.String(50))
    abrangencia = db.Column(db.String(50), nullable=True)
    atualizado = db.Column(db.Boolean, nullable=True)
    data_elaboracao = db.Column(db.String(50), nullable=True)
    vencimento = db.Column(db.String(50), nullable=True)
    numero_sei = db.Column(db.String(50), nullable=True)
    elaboradores = db.Column(db.String(1000), nullable=True)
    marcador = db.Column(db.String(100), nullable=True)
    nome_completo = db.Column(db.String(200), nullable=True)

    versao_atual = db.Column(db.Integer, default=1)
    historico_versoes = db.Column(MutableList.as_mutable(JSON), default=list)
    data_atualizacao = db.Column(db.DateTime)

    def __repr__(self):
        return f"<Documento2 {self.nome} (v{self.versao_atual})>"

    @property
    def versao_efetiva(self):
        return self.versao_atual if self.versao_atual is not None else 1

    @property
    def historico_efetivo(self):
        return self.historico_versoes if self.historico_versoes is not None else []


class Organograma(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True)


class TipoDocumento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True)
