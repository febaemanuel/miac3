"""Povoamento inicial de tabelas de vocabulário e usuários."""
import os

from werkzeug.security import generate_password_hash

from sqlalchemy import inspect, text

from app.extensions import db
from app.models import (
    Abrangencia,
    AbrangenciaSinonimo,
    Documento,
    Organograma,
    OrganizacaoConfig,
    TipoDocumento,
    Usuario,
)


SINONIMOS_EBSERH = {"CHUFC": "HUWC", "CH": "HUWC"}


def _seed_abrangencias():
    existentes = {a.nome for a in Abrangencia.query.all()}
    for (nome,) in db.session.query(Documento.abrangencia).distinct():
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
    for (nome,) in db.session.query(Documento.organograma).distinct():
        if nome and nome not in existentes:
            db.session.add(Organograma(nome=nome))
            existentes.add(nome)


def _enable_extensions():
    if db.engine.dialect.name != "postgresql":
        return
    db.session.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))


def _consolidar_tabela_documento():
    """Migra o esquema antigo (documento legacy + documento2) para tabela única 'documento'.

    Regras:
    - Se existir 'documento2' e 'documento' (legacy), descarta a legacy e renomeia.
    - Se existir só 'documento2', renomeia para 'documento'.
    - Atualiza 'caminho' substituindo 'uploads2/' por 'uploads/'.
    """
    inspector = inspect(db.engine)
    tabelas = set(inspector.get_table_names())

    def colunas(tabela):
        return {c["name"] for c in inspector.get_columns(tabela)}

    if "documento2" in tabelas:
        if "documento" in tabelas:
            cols = colunas("documento")
            eh_legacy = "titulo" in cols and "nome" not in cols
            if eh_legacy:
                db.session.execute(text("DROP TABLE documento"))
                db.session.commit()
            else:
                # já consolidado anteriormente; apenas descarta o duplicado
                db.session.execute(text("DROP TABLE documento2"))
                db.session.commit()
                return
        db.session.execute(text("ALTER TABLE documento2 RENAME TO documento"))
        db.session.commit()
    elif "documento" in tabelas:
        cols = colunas("documento")
        if "titulo" in cols and "nome" not in cols:
            # legacy isolada, sem dados novos: substitui pelo esquema novo
            db.session.execute(text("DROP TABLE documento"))
            db.session.commit()


def _atualizar_caminhos_uploads():
    """Migra caminhos de 'static/uploads2/...' para 'static/uploads/...'."""
    inspector = inspect(db.engine)
    if "documento" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("documento")}
    if "caminho" in cols:
        db.session.execute(text(
            "UPDATE documento SET caminho = REPLACE(caminho, 'uploads2/', 'uploads/') "
            "WHERE caminho LIKE '%uploads2/%'"
        ))
    if "pdf_antigo" in cols:
        db.session.execute(text(
            "UPDATE documento SET pdf_antigo = REPLACE(pdf_antigo, 'uploads2/', 'uploads/') "
            "WHERE pdf_antigo LIKE '%uploads2/%'"
        ))
    db.session.commit()


def _migrate_schema():
    """Adiciona colunas novas em bancos já existentes (idempotente)."""
    _consolidar_tabela_documento()

    inspector = inspect(db.engine)
    dialect = db.engine.dialect.name

    def tem_coluna(tabela, coluna):
        return any(c["name"] == coluna for c in inspector.get_columns(tabela))

    def add_col(tabela, ddl):
        db.session.execute(text(f"ALTER TABLE {tabela} ADD COLUMN {ddl}"))

    if "organograma" in inspector.get_table_names():
        if not tem_coluna("organograma", "nome_completo"):
            add_col("organograma", "nome_completo VARCHAR(200)")
        if not tem_coluna("organograma", "abrangencia_id"):
            add_col("organograma", "abrangencia_id INTEGER REFERENCES abrangencia(id)")

    if "abrangencia" in inspector.get_table_names():
        if not tem_coluna("abrangencia", "cor"):
            default = "'#007bff'" if dialect != "postgresql" else "'#007bff'"
            add_col("abrangencia", f"cor VARCHAR(7) NOT NULL DEFAULT {default}")
        if not tem_coluna("abrangencia", "ordem"):
            add_col("abrangencia", "ordem INTEGER NOT NULL DEFAULT 0")

    db.session.commit()

    _atualizar_caminhos_uploads()


def _backfill_vinculos_e_nomes():
    """Preenche organograma.abrangencia_id e nome_completo a partir dos documentos."""
    orgs_sem_abrang = Organograma.query.filter(Organograma.abrangencia_id.is_(None)).all()
    if orgs_sem_abrang:
        for org in orgs_sem_abrang:
            mais_comum = (
                db.session.query(Documento.abrangencia, db.func.count(Documento.id))
                .filter(Documento.organograma == org.nome)
                .filter(Documento.abrangencia.isnot(None))
                .group_by(Documento.abrangencia)
                .order_by(db.func.count(Documento.id).desc())
                .first()
            )
            if mais_comum:
                abrang = Abrangencia.query.filter_by(nome=mais_comum[0]).first()
                if abrang:
                    org.abrangencia_id = abrang.id

    orgs_sem_nome = Organograma.query.filter(Organograma.nome_completo.is_(None)).all()
    for org in orgs_sem_nome:
        doc_com_nome = (
            Documento.query.filter(Documento.organograma == org.nome)
            .filter(Documento.nome_completo.isnot(None))
            .first()
        )
        if doc_com_nome and doc_com_nome.nome_completo:
            org.nome_completo = doc_com_nome.nome_completo


def _seed_tipos_documento():
    existentes = {t.nome for t in TipoDocumento.query.all()}
    for (nome,) in db.session.query(Documento.tipo_documento).distinct():
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
    _enable_extensions()
    _migrate_schema()
    _seed_abrangencias()
    _seed_organogramas()
    _seed_tipos_documento()
    _seed_usuarios()
    _backfill_vinculos_e_nomes()
    OrganizacaoConfig.get()  # cria singleton com defaults se não existir
    db.session.commit()
