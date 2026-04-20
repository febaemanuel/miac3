"""Carrega configuração da aplicação a partir do .env."""
import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")

    _db_host = os.getenv("DB_HOST")
    _db_port = os.getenv("DB_PORT")
    _db_user = os.getenv("DB_USER")
    _db_password = os.getenv("DB_PASSWORD")
    _db_name = os.getenv("DB_NAME")

    SQLALCHEMY_DATABASE_URI = (
        f"postgresql+psycopg://{_db_user}:{_db_password}@{_db_host}:{_db_port}/{_db_name}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.path.join("static", "uploads")

    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

    GOOGLE_APPLICATION_CREDENTIALS = os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS", "google_credentials.json"
    )


def validate():
    if not Config.SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY ausente no .env. Gere com: "
            'python -c "import secrets; print(secrets.token_hex(32))"'
        )
    os.environ.setdefault(
        "GOOGLE_APPLICATION_CREDENTIALS", Config.GOOGLE_APPLICATION_CREDENTIALS
    )
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
