"""Painel administrativo unificado: organogramas, abrangências, tipos, siglas, marcadores, usuários."""
from flask import flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import (
    Abrangencia,
    AbrangenciaSinonimo,
    Documento2,
    Organograma,
    TipoDocumento,
    Usuario,
)


def _require_admin():
    if "username" not in session or session.get("nivel_acesso") != "elevado":
        return redirect(url_for("login"))
    return None


def init_routes(app):
    @app.route("/miac/admin", methods=["GET"])
    def admin_panel():
        guard = _require_admin()
        if guard:
            return guard

        siglas = (
            db.session.query(
                Documento2.organograma,
                db.func.max(Documento2.nome_completo).label("nome_completo"),
                db.func.count(Documento2.id).label("total_documentos"),
            )
            .group_by(Documento2.organograma)
            .all()
        )
        marcadores = (
            db.session.query(
                Documento2.organograma, Documento2.abrangencia, Documento2.marcador
            )
            .distinct()
            .all()
        )

        return render_template(
            "admin.html",
            organogramas=Organograma.query.order_by(Organograma.nome).all(),
            abrangencias=Abrangencia.query.order_by(Abrangencia.nome).all(),
            sinonimos=AbrangenciaSinonimo.query.all(),
            tipos_documento=TipoDocumento.query.order_by(TipoDocumento.nome).all(),
            usuarios=Usuario.query.order_by(Usuario.username).all(),
            siglas=siglas,
            marcadores=marcadores,
        )

    @app.route("/miac/admin/organograma", methods=["POST"])
    def admin_organograma():
        guard = _require_admin()
        if guard:
            return guard

        acao = request.form.get("acao")
        if acao == "add":
            nome = (request.form.get("nome") or "").strip().upper()
            if nome and not Organograma.query.filter_by(nome=nome).first():
                db.session.add(Organograma(nome=nome))
        elif acao == "remove":
            org = Organograma.query.get(request.form.get("id"))
            if org:
                db.session.delete(org)
        db.session.commit()
        return redirect(url_for("admin_panel") + "#organogramas")

    @app.route("/miac/admin/abrangencia", methods=["POST"])
    def admin_abrangencia():
        guard = _require_admin()
        if guard:
            return guard

        acao = request.form.get("acao")
        if acao == "add":
            nome = (request.form.get("nome") or "").strip().upper()
            if nome and not Abrangencia.query.filter_by(nome=nome).first():
                db.session.add(Abrangencia(nome=nome, ativo=True))
        elif acao == "toggle":
            abrang = Abrangencia.query.get(request.form.get("id"))
            if abrang:
                abrang.ativo = not abrang.ativo
        elif acao == "remove":
            abrang = Abrangencia.query.get(request.form.get("id"))
            if abrang:
                AbrangenciaSinonimo.query.filter_by(para_id=abrang.id).delete()
                db.session.delete(abrang)
        db.session.commit()
        return redirect(url_for("admin_panel") + "#abrangencias")

    @app.route("/miac/admin/sinonimo", methods=["POST"])
    def admin_abrangencia_sinonimo():
        guard = _require_admin()
        if guard:
            return guard

        acao = request.form.get("acao")
        if acao == "add":
            de = (request.form.get("de") or "").strip().upper()
            para_id = request.form.get("para_id")
            if de and para_id and not AbrangenciaSinonimo.query.filter_by(de=de).first():
                db.session.add(AbrangenciaSinonimo(de=de, para_id=int(para_id)))
        elif acao == "remove":
            sin = AbrangenciaSinonimo.query.get(request.form.get("id"))
            if sin:
                db.session.delete(sin)
        db.session.commit()
        return redirect(url_for("admin_panel") + "#abrangencias")

    @app.route("/miac/admin/tipo_documento", methods=["POST"])
    def admin_tipo_documento():
        guard = _require_admin()
        if guard:
            return guard

        acao = request.form.get("acao")
        if acao == "add":
            nome = (request.form.get("nome") or "").strip().upper()
            if nome and not TipoDocumento.query.filter_by(nome=nome).first():
                db.session.add(TipoDocumento(nome=nome))
        elif acao == "remove":
            tipo = TipoDocumento.query.get(request.form.get("id"))
            if tipo:
                db.session.delete(tipo)
        db.session.commit()
        return redirect(url_for("admin_panel") + "#tipos")

    @app.route("/miac/admin/sigla", methods=["POST"])
    def admin_sigla():
        guard = _require_admin()
        if guard:
            return guard

        sigla = (request.form.get("sigla") or "").strip().upper()
        nome_completo = (request.form.get("nome_completo") or "").strip()
        if sigla:
            Documento2.query.filter_by(organograma=sigla).update(
                {"nome_completo": nome_completo}
            )
            db.session.commit()
        return redirect(url_for("admin_panel") + "#siglas")

    @app.route("/miac/admin/marcador", methods=["POST"])
    def admin_marcador():
        guard = _require_admin()
        if guard:
            return guard

        for key, value in request.form.items():
            if key.startswith("marcador_"):
                _, organograma_nome, abrangencia_nome = key.split("_", 2)
                Documento2.query.filter_by(
                    organograma=organograma_nome, abrangencia=abrangencia_nome
                ).update({"marcador": value})
        db.session.commit()
        return redirect(url_for("admin_panel") + "#marcadores")

    @app.route("/miac/admin/usuario", methods=["POST"])
    def admin_usuario():
        guard = _require_admin()
        if guard:
            return guard

        acao = request.form.get("acao")
        if acao == "add":
            username = (request.form.get("username") or "").strip()
            senha = request.form.get("senha") or ""
            nivel = request.form.get("nivel_acesso", "padrao")
            if username and senha and not Usuario.query.filter_by(username=username).first():
                db.session.add(Usuario(
                    username=username,
                    senha_hash=generate_password_hash(senha),
                    nivel_acesso=nivel if nivel in ("padrao", "elevado") else "padrao",
                ))
        elif acao == "toggle":
            u = Usuario.query.get(request.form.get("id"))
            if u and u.username != session.get("username"):
                u.ativo = not u.ativo
        elif acao == "remove":
            u = Usuario.query.get(request.form.get("id"))
            if u and u.username != session.get("username"):
                db.session.delete(u)
        elif acao == "reset_senha":
            u = Usuario.query.get(request.form.get("id"))
            nova = request.form.get("senha") or ""
            if u and nova:
                u.senha_hash = generate_password_hash(nova)
        elif acao == "alterar_nivel":
            u = Usuario.query.get(request.form.get("id"))
            nivel = request.form.get("nivel_acesso")
            if u and nivel in ("padrao", "elevado") and u.username != session.get("username"):
                u.nivel_acesso = nivel
        db.session.commit()
        return redirect(url_for("admin_panel") + "#usuarios")
