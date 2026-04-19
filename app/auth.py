"""Autenticação baseada em tabela Usuario."""
from flask import redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from app.models import Usuario


def login_user(username, password):
    user = Usuario.query.filter_by(username=username, ativo=True).first()
    if user and check_password_hash(user.senha_hash, password):
        session["username"] = user.username
        session["nivel_acesso"] = user.nivel_acesso
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
