import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration."""
    SECRET_KEY = os.getenv("SECRET_KEY") or "dev-secret-key-change-in-production"

    # Database
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "miac")

    SQLALCHEMY_DATABASE_URI = (
        f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Upload
    UPLOAD_FOLDER = os.path.join("static", "uploads2")
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
    ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx"}

    # AI APIs
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    CHATGPT_API_KEY = os.getenv("CHATGPT_API_KEY", "")

    # App URL
    BASE_URL = os.getenv("BASE_URL", "https://hg.huwc.ufc.br")

    # Users (temporary - should be migrated to database)
    USERS = {
        "usuario": {"senha": "senha123", "nivel_acesso": "padrao"},
        "admin": {"senha": "Qualidade@admin!", "nivel_acesso": "elevado"},
    }
