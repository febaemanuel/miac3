from functools import wraps
from flask import session, redirect, url_for, jsonify, request


def login_required(f):
    """Decorator that requires user to be logged in."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "username" not in session:
            if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": "Não autenticado"}), 401
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator that requires admin (elevated) access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "username" not in session or session.get("nivel_acesso") != "elevado":
            if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": "Acesso negado"}), 403
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function
