"""Factory da aplicação Flask."""
import logging

from flask import Flask
from sqlalchemy import inspect

from app.config import Config, validate
from app.extensions import db
from app.services.dates import expired_duration_filter


def _setup_logging(app):
    level = logging.DEBUG if app.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    app.logger.setLevel(level)


def create_app(config_class=Config):
    validate()

    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    app.config.from_object(config_class)
    app.secret_key = app.config["SECRET_KEY"]

    _setup_logging(app)

    db.init_app(app)

    # Importa modelos antes de create_all para registrá-los no metadata.
    from app import models  # noqa: F401

    with app.app_context():
        inspector = inspect(db.engine)
        if not inspector.has_table("documento") or not inspector.has_table("documento2"):
            db.create_all()
            app.logger.info("Banco de dados e tabelas criados.")
        else:
            db.create_all()
            app.logger.info("Banco de dados já existente; garantindo tabelas novas.")

        from app.seed import run_seeds
        run_seeds()

    app.add_template_filter(expired_duration_filter, name="expired_duration")

    from app.models import OrganizacaoConfig

    @app.context_processor
    def inject_org_config():
        return {"org_config": OrganizacaoConfig.get()}

    from app import auth
    from app.routes import admin, api, documentos, main, relatorios

    auth.init_routes(app)
    main.init_routes(app)
    documentos.init_routes(app)
    relatorios.init_routes(app)
    admin.init_routes(app)
    api.init_routes(app)

    return app
