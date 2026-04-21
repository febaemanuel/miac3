"""Rotas principais: index, buscas e relações."""
from flask import (
    current_app,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from sqlalchemy import or_

from app.extensions import db
from app.models import Documento
from app.services.dates import normalizar_texto


def init_routes(app):
    @app.route("/miac/", methods=["GET", "POST"])
    def index():
        if "username" not in session:
            return redirect(url_for("login"))
        return render_template("index.html")

    @app.route("/miac/relacao_documentos")
    def relacao_documentos():
        if "username" not in session:
            return redirect(url_for("login"))
        documentos = Documento.query.all()
        return render_template("relacao_documentos.html", documentos=documentos)

    @app.route("/miac/buscar", methods=["GET"])
    def buscar():
        nome = request.args.get("nome", "").strip()
        organograma = request.args.get("organograma", "").strip()
        tipo_documento = request.args.get("tipo_documento", "").strip()
        abrangencia = request.args.get("abrangencia", "").strip()
        search_organograma = request.args.get("search_organograma", "").strip().lower()

        query = Documento.query

        if nome:
            termo_busca = normalizar_texto(nome)
            query = query.filter(
                db.func.unaccent(Documento.nome).ilike(f"%{termo_busca}%")
            )

        if organograma:
            termo_busca = normalizar_texto(organograma)
            query = query.filter(
                or_(
                    db.func.unaccent(Documento.organograma).ilike(f"%{termo_busca}%"),
                    db.func.unaccent(Documento.nome_completo).ilike(f"%{termo_busca}%"),
                )
            )

        if tipo_documento:
            termo_busca = normalizar_texto(tipo_documento)
            query = query.filter(
                db.func.unaccent(Documento.tipo_documento).ilike(f"%{termo_busca}%")
            )

        if abrangencia:
            query = query.filter(Documento.abrangencia == abrangencia)

        documentos = query.all()

        if search_organograma:
            documentos = [
                doc
                for doc in documentos
                if (
                    search_organograma in normalizar_texto(doc.organograma)
                    or (
                        doc.nome_completo
                        and search_organograma in normalizar_texto(doc.nome_completo)
                    )
                )
            ]

        documentos_agrupados = {}
        filtro_ativo = bool(
            nome or organograma or tipo_documento or search_organograma
        )
        if not filtro_ativo:
            for doc in documentos:
                marcador = doc.marcador if doc.marcador else "Sem Marcador"
                documentos_agrupados.setdefault(marcador, {})
                documentos_agrupados[marcador].setdefault(doc.organograma, {})
                documentos_agrupados[marcador][doc.organograma].setdefault(
                    doc.tipo_documento, []
                )
                documentos_agrupados[marcador][doc.organograma][
                    doc.tipo_documento
                ].append(doc)

        organogramas_completos = (
            db.session.query(Documento.organograma, Documento.nome_completo)
            .distinct()
            .all()
        )
        organogramas_formatados = [
            {"sigla": org[0], "nome_completo": org[1]} for org in organogramas_completos
        ]
        organogramas_formatados.sort(
            key=lambda x: (x["nome_completo"] or x["sigla"]).lower()
        )

        tipos_documento_unicos = {
            doc.tipo_documento for doc in documentos if doc.tipo_documento
        }
        tipos_documento_list = sorted(tipos_documento_unicos)

        return render_template(
            "partials/document_list.html",
            documentos_agrupados=documentos_agrupados,
            documentos=documentos,
            exibir_lista=filtro_ativo,
            abrangencia=abrangencia,
            organogramas=organogramas_formatados,
            tipos_documento=tipos_documento_list,
            organograma_filtro=organograma,
            tipo_documento_filtro=tipo_documento,
        )

    @app.route("/miac/carregar_documentos_modal", methods=["GET"])
    def carregar_documentos_modal():
        organograma = request.args.get("organograma", "").strip()
        abrangencia = request.args.get("abrangencia", "").strip()

        documentos = Documento.query.filter_by(
            organograma=organograma, abrangencia=abrangencia
        ).all()

        documentos_por_tipo = {}
        for doc in documentos:
            documentos_por_tipo.setdefault(doc.tipo_documento, []).append(doc)

        return render_template(
            "partials/modal_content.html",
            organograma=organograma,
            documentos_por_tipo=documentos_por_tipo,
        )

    @app.route("/miac/static/<path:filename>")
    def static_files(filename):
        return send_from_directory(current_app.static_folder, filename)
