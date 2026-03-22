import logging

from sqlalchemy import JSON, Index
from sqlalchemy.ext.mutable import MutableList

from app.extensions import db

logger = logging.getLogger(__name__)


class Documento(db.Model):
    """Legacy document model (kept for backward compatibility)."""
    __tablename__ = "documento"

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
    """Primary document model with versioning support."""
    __tablename__ = "documento2"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(400), nullable=False)
    organograma = db.Column(db.String(100), nullable=False, index=True)
    tipo_documento = db.Column(db.String(100), nullable=False, index=True)
    caminho = db.Column(db.String(200))
    pdf_antigo = db.Column(db.String(200), nullable=True)
    data_publicacao = db.Column(db.String(50))
    abrangencia = db.Column(db.String(50), nullable=True, index=True)
    atualizado = db.Column(db.Boolean, nullable=True, index=True)
    data_elaboracao = db.Column(db.String(50), nullable=True)
    vencimento = db.Column(db.String(50), nullable=True)
    numero_sei = db.Column(db.String(50), nullable=True)
    elaboradores = db.Column(db.String(1000), nullable=True)
    marcador = db.Column(db.String(100), nullable=True, index=True)
    nome_completo = db.Column(db.String(200), nullable=True)
    versao_atual = db.Column(db.Integer, default=1)
    historico_versoes = db.Column(MutableList.as_mutable(JSON), default=list)
    data_atualizacao = db.Column(db.DateTime)

    # Composite index for common query patterns
    __table_args__ = (
        Index("ix_doc2_org_abrangencia", "organograma", "abrangencia"),
    )

    def __repr__(self):
        return f"<Documento2 {self.nome} (v{self.versao_atual})>"

    @property
    def versao_efetiva(self):
        return self.versao_atual if self.versao_atual is not None else 1

    @property
    def historico_efetivo(self):
        return self.historico_versoes if self.historico_versoes is not None else []


class Organograma(db.Model):
    """Organization unit lookup table."""
    __tablename__ = "organograma"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)


class TipoDocumento(db.Model):
    """Document type lookup table."""
    __tablename__ = "tipo_documento"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)


def criar_banco_de_dados(app):
    """Creates database tables if they don't exist."""
    with app.app_context():
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        if not inspector.has_table("documento") or not inspector.has_table("documento2"):
            db.create_all()
            logger.info("Database tables created successfully!")
        else:
            logger.info("Database already exists.")
