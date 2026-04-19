"""Rotas de gestão: siglas, marcadores e opções (organogramas/tipos)."""
from flask import flash, redirect, render_template, request, session, url_for

from app.extensions import db
from app.models import Documento2, Organograma, TipoDocumento


def init_routes(app):
    @app.route("/miac/gerenciar_siglas", methods=["GET", "POST"])
    def gerenciar_siglas():
        if "username" not in session or session.get("nivel_acesso") != "elevado":
            return redirect(url_for("login"))

        siglas_com_contagem = (
            db.session.query(
                Documento2.organograma,
                db.func.max(Documento2.nome_completo).label("nome_completo"),
                db.func.count(Documento2.id).label("total_documentos"),
            )
            .group_by(Documento2.organograma)
            .all()
        )

        if request.method == "POST":
            sigla = request.form.get("sigla").strip().upper()
            nome_completo = request.form.get("nome_completo").strip()
            Documento2.query.filter_by(organograma=sigla).update(
                {"nome_completo": nome_completo}
            )
            db.session.commit()
            flash("Sigla atualizada com sucesso!", "success")
            return redirect(url_for("gerenciar_siglas"))

        return render_template(
            "gerenciar_siglas.html", siglas=siglas_com_contagem
        )

    @app.route("/miac/gerenciar_marcadores", methods=["GET", "POST"])
    def gerenciar_marcadores():
        if "username" not in session or session.get("nivel_acesso") != "elevado":
            return redirect(url_for("login"))

        if request.method == "POST":
            for key, value in request.form.items():
                if key.startswith("marcador_"):
                    parts = key.split("_")
                    organograma_nome = parts[1]
                    abrangencia = parts[2]
                    Documento2.query.filter_by(
                        organograma=organograma_nome, abrangencia=abrangencia
                    ).update({"marcador": value})

            novo_organograma = request.form.get("novo_organograma")
            novo_abrangencia = request.form.get("novo_abrangencia")
            novo_marcador = request.form.get("novo_marcador")
            if novo_organograma and novo_abrangencia and novo_marcador:
                Documento2.query.filter_by(
                    organograma=novo_organograma, abrangencia=novo_abrangencia
                ).update({"marcador": novo_marcador})

            db.session.commit()
            flash("Marcadores atualizados com sucesso!", "success")
            return redirect(url_for("gerenciar_marcadores"))

        organogramas_unicos = (
            db.session.query(
                Documento2.organograma,
                Documento2.abrangencia,
                Documento2.marcador,
            )
            .distinct()
            .all()
        )
        return render_template(
            "gerenciar_marcadores.html", organogramas=organogramas_unicos
        )

    @app.route("/miac/gerenciar_opcoes", methods=["GET", "POST"])
    def gerenciar_opcoes():
        if "username" not in session:
            return redirect(url_for("login"))

        if request.method == "POST":
            tipo = request.form.get("tipo")
            nome = request.form.get("nome")
            if tipo == "organograma":
                db.session.add(Organograma(nome=nome))
            elif tipo == "tipo_documento":
                db.session.add(TipoDocumento(nome=nome))
            db.session.commit()
            return redirect(url_for("gerenciar_opcoes"))

        organogramas = Organograma.query.all()
        tipos_documento = TipoDocumento.query.all()
        return render_template(
            "gerenciar_opcoes.html",
            organogramas=organogramas,
            tipos_documento=tipos_documento,
        )

    @app.route("/miac/remover_opcao/<int:id>/<tipo>")
    def remover_opcao(id, tipo):
        if "username" not in session:
            return redirect(url_for("login"))

        if tipo == "organograma":
            opcao = Organograma.query.get(id)
        elif tipo == "tipo_documento":
            opcao = TipoDocumento.query.get(id)
        else:
            opcao = None

        if opcao:
            db.session.delete(opcao)
            db.session.commit()

        return redirect(url_for("gerenciar_opcoes"))
