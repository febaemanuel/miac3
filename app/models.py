"""Modelos SQLAlchemy."""
from sqlalchemy import JSON
from sqlalchemy.ext.mutable import MutableDict, MutableList

from app.extensions import db


class Documento(db.Model):
    """Documento publicado, com versionamento."""

    __tablename__ = "documento"

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

    campos_extras = db.Column(MutableDict.as_mutable(JSON), default=dict)

    def __repr__(self):
        return f"<Documento {self.nome} (v{self.versao_atual})>"

    @property
    def versao_efetiva(self):
        return self.versao_atual if self.versao_atual is not None else 1

    @property
    def historico_efetivo(self):
        return self.historico_versoes if self.historico_versoes is not None else []


class Organograma(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True)
    nome_completo = db.Column(db.String(200), nullable=True)
    abrangencia_id = db.Column(
        db.Integer, db.ForeignKey("abrangencia.id"), nullable=True
    )
    abrangencia = db.relationship("Abrangencia", backref="organogramas")


class TipoDocumento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True)


class Abrangencia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), unique=True, nullable=False)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    cor = db.Column(db.String(7), nullable=False, default="#007bff")
    ordem = db.Column(db.Integer, nullable=False, default=0)


class AbrangenciaSinonimo(db.Model):
    __tablename__ = "abrangencia_sinonimo"
    id = db.Column(db.Integer, primary_key=True)
    de = db.Column(db.String(50), nullable=False, index=True)
    para_id = db.Column(
        db.Integer, db.ForeignKey("abrangencia.id"), nullable=False
    )
    para = db.relationship("Abrangencia")


class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    nivel_acesso = db.Column(db.String(20), nullable=False, default="padrao")
    ativo = db.Column(db.Boolean, default=True, nullable=False)


class OrganizacaoConfig(db.Model):
    """Identidade visual e institucional. Singleton (sempre id=1)."""
    __tablename__ = "organizacao_config"
    id = db.Column(db.Integer, primary_key=True)
    nome_empresa = db.Column(db.String(150), nullable=False, default="MIAC")
    sigla_app = db.Column(db.String(30), nullable=False, default="DOC'S-UGQ")
    cor_primaria = db.Column(db.String(7), nullable=False, default="#007bff")
    cor_sidebar = db.Column(db.String(7), nullable=False, default="#34495e")
    logo_path = db.Column(db.String(200), nullable=True)
    rodape = db.Column(
        db.String(300), nullable=False,
        default="Versão 1.0.0 | Desenvolvido por MIAC | Suporte: suporte@miac.com.br",
    )

    @classmethod
    def get(cls):
        instancia = cls.query.get(1)
        if not instancia:
            instancia = cls(id=1)
            db.session.add(instancia)
            db.session.commit()
        return instancia


class IaConfig(db.Model):
    """Configuração da integração com IA. Singleton (sempre id=1)."""
    __tablename__ = "ia_config"
    id = db.Column(db.Integer, primary_key=True)
    modelo_padrao = db.Column(db.String(20), nullable=False, default="deepseek")
    deepseek_api_key = db.Column(db.String(255), nullable=True)
    openai_api_key = db.Column(db.String(255), nullable=True)
    prompt_extracao = db.Column(db.Text, nullable=True)

    @classmethod
    def get(cls):
        instancia = cls.query.get(1)
        if not instancia:
            instancia = cls(id=1)
            db.session.add(instancia)
            db.session.commit()
        return instancia


class CampoExtracao(db.Model):
    """Campo dinâmico extraído pela IA e exibido no formulário de publicação."""
    __tablename__ = "campo_extracao"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(60), unique=True, nullable=False)
    rotulo = db.Column(db.String(120), nullable=False)
    tipo = db.Column(db.String(20), nullable=False, default="texto")
    opcoes = db.Column(JSON, nullable=True)
    obrigatorio = db.Column(db.Boolean, nullable=False, default=False)
    ordem = db.Column(db.Integer, nullable=False, default=0)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    mostrar_na_listagem = db.Column(db.Boolean, nullable=False, default=False)
    instrucao_ia = db.Column(db.Text, nullable=True)


class FiltroPublicados(db.Model):
    """Filtro configurável da sidebar da página de documentos publicados."""
    __tablename__ = "filtro_publicados"
    id = db.Column(db.Integer, primary_key=True)
    rotulo = db.Column(db.String(120), nullable=False)
    tipo = db.Column(db.String(20), nullable=False, default="padrao")  # padrao | extra
    campo_ref = db.Column(db.String(60), nullable=False)
    ordem = db.Column(db.Integer, nullable=False, default=0)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    icone = db.Column(db.String(40), nullable=True)
