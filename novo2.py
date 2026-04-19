"""Entry point da aplicação MIAC. Preserva o caminho histórico `novo2.py`."""
from waitress import serve

from app import create_app

app = create_app()


if __name__ == "__main__":
    print("Rodando")
    serve(app, host="0.0.0.0", port=8090)
