import logging
import os

from flask import Flask

from app.extensions import db
from app.models import Documento, Documento2, Organograma, TipoDocumento
from config import Config

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def create_app(config_class=Config):
    """Application factory pattern."""
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"),
        static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "static"),
    )
    app.config.from_object(config_class)

    # Ensure upload folder exists
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Initialize extensions
    db.init_app(app)

    # Register template filters
    from app.utils import expired_duration
    app.add_template_filter(expired_duration, "expired_duration")

    # Register blueprints
    from app.auth.routes import auth_bp
    from app.documents.routes import documents_bp
    from app.admin.routes import admin_bp
    from app.api.routes import api_bp
    from app.reports.routes import reports_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(reports_bp)

    # Create database tables if needed
    with app.app_context():
        from sqlalchemy import inspect as sa_inspect
        inspector = sa_inspect(db.engine)
        if not inspector.has_table("documento2"):
            db.create_all()
            logger.info("Database tables created.")

    return app
