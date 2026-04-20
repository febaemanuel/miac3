"""Painel administrativo unificado: organogramas, abrangências, tipos, siglas, marcadores, usuários."""
from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import generate_password_hash

import os

from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (
    Abrangencia,
    AbrangenciaSinonimo,
    Documento,
    Organograma,
    OrganizacaoConfig,
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
                Documento.organograma,
                db.func.max(Documento.nome_completo).label("nome_completo"),
                db.func.count(Documento.id).label("total_documentos"),
            )
            .group_by(Documento.organograma)
            .all()
        )
        marcadores = (
            db.session.query(
                Documento.organograma, Documento.abrangencia, Documento.marcador
            )
            .distinct()
            .all()
        )

        abrangencias = (
            Abrangencia.query.order_by(Abrangencia.ordem, Abrangencia.nome).all()
        )
        organogramas = Organograma.query.order_by(Organograma.nome).all()
        organogramas_por_abrangencia = {a.id: [] for a in abrangencias}
        organogramas_orfaos = []
        for org in organogramas:
            if org.abrangencia_id and org.abrangencia_id in organogramas_por_abrangencia:
                organogramas_por_abrangencia[org.abrangencia_id].append(org)
            else:
                organogramas_orfaos.append(org)

        return render_template(
            "admin.html",
            organogramas=organogramas,
            abrangencias=abrangencias,
            organogramas_por_abrangencia=organogramas_por_abrangencia,
            organogramas_orfaos=organogramas_orfaos,
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
            abrangencia_id = request.form.get("abrangencia_id") or None
            nome_completo = (request.form.get("nome_completo") or "").strip() or None
            if nome and not Organograma.query.filter_by(nome=nome).first():
                db.session.add(
                    Organograma(
                        nome=nome,
                        abrangencia_id=int(abrangencia_id) if abrangencia_id else None,
                        nome_completo=nome_completo,
                    )
                )
        elif acao == "update":
            org = Organograma.query.get(request.form.get("id"))
            if org:
                if "abrangencia_id" in request.form:
                    novo = request.form.get("abrangencia_id") or None
                    org.abrangencia_id = int(novo) if novo else None
                if "nome_completo" in request.form:
                    novo_nome = (request.form.get("nome_completo") or "").strip()
                    org.nome_completo = novo_nome or None
        elif acao == "remove":
            org = Organograma.query.get(request.form.get("id"))
            if org:
                db.session.delete(org)
        db.session.commit()
        return redirect(url_for("admin_panel") + "#estrutura")

    @app.route("/miac/admin/abrangencia", methods=["POST"])
    def admin_abrangencia():
        guard = _require_admin()
        if guard:
            return guard

        acao = request.form.get("acao")
        if acao == "add":
            nome = (request.form.get("nome") or "").strip().upper()
            cor = (request.form.get("cor") or "#007bff").strip()
            if nome and not Abrangencia.query.filter_by(nome=nome).first():
                ordem = (db.session.query(db.func.max(Abrangencia.ordem)).scalar() or 0) + 1
                db.session.add(Abrangencia(nome=nome, ativo=True, cor=cor, ordem=ordem))
        elif acao == "toggle":
            abrang = Abrangencia.query.get(request.form.get("id"))
            if abrang:
                abrang.ativo = not abrang.ativo
        elif acao == "update":
            abrang = Abrangencia.query.get(request.form.get("id"))
            if abrang:
                cor = (request.form.get("cor") or "").strip()
                if cor:
                    abrang.cor = cor
        elif acao == "remove":
            abrang = Abrangencia.query.get(request.form.get("id"))
            if abrang:
                AbrangenciaSinonimo.query.filter_by(para_id=abrang.id).delete()
                Organograma.query.filter_by(abrangencia_id=abrang.id).update(
                    {"abrangencia_id": None}
                )
                db.session.delete(abrang)
        db.session.commit()
        return redirect(url_for("admin_panel") + "#estrutura")

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
        return redirect(url_for("admin_panel") + "#estrutura")

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
        return redirect(url_for("admin_panel") + "#estrutura")

    @app.route("/miac/admin/sigla", methods=["POST"])
    def admin_sigla():
        guard = _require_admin()
        if guard:
            return guard

        sigla = (request.form.get("sigla") or "").strip().upper()
        nome_completo = (request.form.get("nome_completo") or "").strip()
        if sigla:
            Documento.query.filter_by(organograma=sigla).update(
                {"nome_completo": nome_completo}
            )
            db.session.commit()
        return redirect(url_for("admin_panel") + "#dados")

    @app.route("/miac/admin/marcador", methods=["POST"])
    def admin_marcador():
        guard = _require_admin()
        if guard:
            return guard

        for key, value in request.form.items():
            if key.startswith("marcador_"):
                _, organograma_nome, abrangencia_nome = key.split("_", 2)
                Documento.query.filter_by(
                    organograma=organograma_nome, abrangencia=abrangencia_nome
                ).update({"marcador": value})
        db.session.commit()
        return redirect(url_for("admin_panel") + "#dados")

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

    @app.route("/miac/admin/identidade", methods=["POST"])
    def admin_identidade():
        guard = _require_admin()
        if guard:
            return guard

        org = OrganizacaoConfig.get()
        org.nome_empresa = (request.form.get("nome_empresa") or org.nome_empresa).strip()
        org.sigla_app = (request.form.get("sigla_app") or org.sigla_app).strip()
        org.cor_primaria = (request.form.get("cor_primaria") or org.cor_primaria).strip()
        org.cor_sidebar = (request.form.get("cor_sidebar") or org.cor_sidebar).strip()
        rodape = request.form.get("rodape")
        if rodape is not None:
            org.rodape = rodape.strip()

        logo = request.files.get("logo")
        if logo and logo.filename:
            nome = secure_filename(logo.filename)
            destino_dir = os.path.join(
                current_app.root_path, "..", "static", "branding"
            )
            os.makedirs(destino_dir, exist_ok=True)
            caminho_abs = os.path.join(destino_dir, nome)
            logo.save(caminho_abs)
            org.logo_path = f"branding/{nome}"

        db.session.commit()
        flash("Identidade atualizada.", "success")
        return redirect(url_for("admin_panel") + "#identidade")
