"""Authentication routes."""
import logging

from flask import Blueprint, render_template, request, redirect, url_for, session

from flask import current_app

auth_bp = Blueprint("auth", __name__, url_prefix="/miac")
logger = logging.getLogger(__name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "username" in session:
        return redirect(url_for("documents.index"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        users = current_app.config["USERS"]
        if username in users and users[username]["senha"] == password:
            session["username"] = username
            session["nivel_acesso"] = users[username]["nivel_acesso"]
            return redirect(url_for("documents.index"))
        else:
            return render_template("login.html", error="Usuário ou senha inválidos")

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.pop("username", None)
    session.pop("nivel_acesso", None)
    return redirect(url_for("auth.login"))
