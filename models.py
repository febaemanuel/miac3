import logging
from sqlalchemy import inspect, JSON
from sqlalchemy.ext.mutable import MutableList

from extensions import db

logger = logging.getLogger(__name__)


class Documento(db.Model):
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
    # Novo campo: HUWC ou MEAC
    abrangencia = db.Column(db.String(50), nullable=True)
    # Novo campo: True (Atualizado) ou False (Desatualizado)
    atualizado = db.Column(db.Boolean, nullable=True)


class Documento2(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(400))  # Nome do arquivo PDF
    organograma = db.Column(db.String(100))  # Escolha do Organograma
    tipo_documento = db.Column(db.String(100))  # Escolha do Tipo de Documento
    caminho = db.Column(db.String(200))  # Caminho do arquivo PDF atual
    pdf_antigo = db.Column(db.String(200), nullable=True)  # Versão anterior imediata
    data_publicacao = db.Column(db.String(50))  # Data de publicação
    abrangencia = db.Column(db.String(50), nullable=True)  # HUWC ou MEAC
    atualizado = db.Column(
        db.Boolean, nullable=True
    )  # True (Atualizado) ou False (Desatualizado)
    data_elaboracao = db.Column(db.String(50), nullable=True)  # Data de Elaboração
    vencimento = db.Column(db.String(50), nullable=True)  # Data de Validade
    numero_sei = db.Column(db.String(50), nullable=True)  # Número SEI
    elaboradores = db.Column(db.String(1000), nullable=True)  # Elaboradores
    marcador = db.Column(db.String(100), nullable=True)  # Marcador
    nome_completo = db.Column(db.String(200), nullable=True)  # Adicione esta linha

    # Novos campos para versionamento avançado
    versao_atual = db.Column(db.Integer, default=1)  # Número da versão atual
    historico_versoes = db.Column(MutableList.as_mutable(JSON), default=lambda: [])
    data_atualizacao = db.Column(db.DateTime)  # Data da última atualização

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


# Modelo para Tipo de Documento


class TipoDocumento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True)


# Função para criar o banco de dados e as tabelas


def criar_banco_de_dados(app):
    with app.app_context():
        # Verifica se o banco de dados já existe
        inspector = inspect(db.engine)
        if not inspector.has_table("documento") or not inspector.has_table(
            "documento2"
        ):
            # Cria todas as tabelas definidas nos modelos
            db.create_all()
            logger.info("Banco de dados e tabelas criados com sucesso!")
        else:
            logger.info("Banco de dados já existe.")
