"""Autenticação baseada em credenciais do .env (hash werkzeug scrypt)."""
import os

from flask import redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash


def _load_users():
    """Carrega usuários do .env. Cada usuário tem username, hash e nível."""
    definicoes = [
        ("USER_PADRAO_USERNAME", "USER_PADRAO_HASH", "padrao"),
        ("USER_ADMIN_USERNAME", "USER_ADMIN_HASH", "elevado"),
    ]
    carregados = {}
    for env_user, env_hash, nivel in definicoes:
        username = os.getenv(env_user)
        password_hash = os.getenv(env_hash)
        if username and password_hash:
            carregados[username] = {"hash": password_hash, "nivel_acesso": nivel}
    if not carregados:
        raise RuntimeError(
            "Nenhum usuário configurado. Defina USER_*_USERNAME e USER_*_HASH no .env."
        )
    return carregados


users = _load_users()


def login_user(username, password):
    user = users.get(username)
    if user and check_password_hash(user["hash"], password):
        session["username"] = username
        session["nivel_acesso"] = user["nivel_acesso"]
        return True
    return False


def init_routes(app):
    @app.route("/miac/login", methods=["GET", "POST"])
    def login():
        if "username" in session:
            return redirect(url_for("index"))

        if request.method == "POST":
            username = request.form["username"]
            password = request.form["password"]
            if login_user(username, password):
                return redirect(url_for("index"))
            return render_template("login.html", error="Usuário ou senha inválidos")

        return render_template("login.html")

    @app.route("/miac/logout")
    def logout():
        session.pop("username", None)
        return redirect(url_for("login"))
