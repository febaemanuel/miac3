"""Admin management routes."""
import logging

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash,
)

from app.decorators import admin_required
from app.extensions import db
from app.models import Documento2, Organograma, TipoDocumento

admin_bp = Blueprint("admin", __name__, url_prefix="/miac")
logger = logging.getLogger(__name__)


@admin_bp.route("/gerenciar_siglas", methods=["GET", "POST"])
@admin_required
def gerenciar_siglas():
    siglas_com_contagem = db.session.query(
        Documento2.organograma,
        db.func.max(Documento2.nome_completo).label("nome_completo"),
        db.func.count(Documento2.id).label("total_documentos"),
    ).group_by(Documento2.organograma).all()

    if request.method == "POST":
        sigla = (request.form.get("sigla") or "").strip().upper()
        nome_completo = (request.form.get("nome_completo") or "").strip()

        if not sigla:
            flash("Sigla não pode ser vazia.", "error")
            return redirect(url_for("admin.gerenciar_siglas"))

        Documento2.query.filter_by(organograma=sigla).update(
            {"nome_completo": nome_completo}
        )
        db.session.commit()
        flash("Sigla atualizada com sucesso!", "success")
        return redirect(url_for("admin.gerenciar_siglas"))

    return render_template("gerenciar_siglas.html", siglas=siglas_com_contagem)


@admin_bp.route("/gerenciar_marcadores", methods=["GET", "POST"])
@admin_required
def gerenciar_marcadores():
    if request.method == "POST":
        for key, value in request.form.items():
            if key.startswith("marcador_"):
                # key format: marcador_{organograma}_{abrangencia}
                # organograma can contain underscores; abrangencia (HUWC/MEAC) cannot
                rest = key[len("marcador_"):]
                organograma_nome, _, abrangencia = rest.rpartition("_")
                if not organograma_nome or not abrangencia:
                    continue

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
        return redirect(url_for("admin.gerenciar_marcadores"))

    organogramas_unicos = (
        db.session.query(
            Documento2.organograma, Documento2.abrangencia, Documento2.marcador
        )
        .distinct()
        .all()
    )

    return render_template(
        "gerenciar_marcadores.html", organogramas=organogramas_unicos
    )


@admin_bp.route("/gerenciar_opcoes", methods=["GET", "POST"])
@admin_required
def gerenciar_opcoes():
    if request.method == "POST":
        tipo = request.form.get("tipo")
        nome = request.form.get("nome", "").strip()

        if not nome:
            flash("Nome não pode ser vazio.", "error")
            return redirect(url_for("admin.gerenciar_opcoes"))

        try:
            if tipo == "organograma":
                db.session.add(Organograma(nome=nome))
            elif tipo == "tipo_documento":
                db.session.add(TipoDocumento(nome=nome))
            db.session.commit()
            flash("Item adicionado com sucesso!", "success")
        except Exception:
            db.session.rollback()
            flash("Erro: item já existe ou dados inválidos.", "error")
        return redirect(url_for("admin.gerenciar_opcoes"))

    organogramas = Organograma.query.all()
    tipos_documento = TipoDocumento.query.all()

    return render_template(
        "gerenciar_opcoes.html",
        organogramas=organogramas,
        tipos_documento=tipos_documento,
    )


@admin_bp.route("/remover_opcao/<int:id>/<tipo>")
@admin_required
def remover_opcao(id, tipo):
    if tipo == "organograma":
        opcao = db.session.get(Organograma, id)
    elif tipo == "tipo_documento":
        opcao = db.session.get(TipoDocumento, id)
    else:
        return "Tipo inválido", 400

    if opcao:
        db.session.delete(opcao)
        db.session.commit()

    return redirect(url_for("admin.gerenciar_opcoes"))
