"""Extensões Flask compartilhadas. Instanciadas sem app para evitar ciclos."""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
