"""Rotas principais: index, lista, buscas e relações."""
from flask import (
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from sqlalchemy import or_

from app.extensions import db
from app.models import Documento, Documento2
from app.services.dates import normalizar_texto


def init_routes(app):
    @app.route("/miac/", methods=["GET", "POST"])
    def index():
        if "username" not in session:
            return redirect(url_for("login"))

        titulo = request.args.get("titulo", "")
        autor_id = request.args.get("autor", "")
        data = request.args.get("data", "")

        query = Documento.query
        if titulo:
            query = query.filter(Documento.titulo.ilike(f"%{titulo}%"))
        if autor_id:
            query = query.filter(Documento.elaboradores.ilike(f"%{autor_id}%"))
        if data:
            query = query.filter(Documento.data_publicacao == data)

        documentos = query.all()
        return render_template("index.html", documentos=documentos)

    @app.route("/miac/lista")
    def lista():
        if "username" not in session:
            return redirect(url_for("login"))
        return render_template("lista.html")

    @app.route("/miac/relacao")
    def relacao():
        if "username" not in session:
            return redirect(url_for("login"))
        documentos = Documento.query.all()
        return render_template("relacao.html", documentos=documentos)

    @app.route("/miac/relacao_documentos")
    def relacao_documentos():
        if "username" not in session:
            return redirect(url_for("login"))
        documentos = Documento2.query.all()
        return render_template("relacao_documentos.html", documentos=documentos)

    @app.route("/miac/buscar", methods=["GET"])
    def buscar():
        if "username" not in session:
            return jsonify({"error": "Usuário não autenticado"}), 403

        titulo = request.args.get("titulo", "").strip()
        autor = request.args.get("autor", "").strip()
        data = request.args.get("data", "").strip()

        query = Documento.query
        if titulo:
            query = query.filter(Documento.titulo.ilike(f"%{titulo}%"))
        if autor:
            query = query.filter(Documento.elaboradores.ilike(f"%{autor}%"))
        if data:
            query = query.filter(Documento.data_publicacao == data)

        documentos = query.all()
        return render_template("partials/document_list.html", documentos=documentos)

    @app.route("/miac/buscar2", methods=["GET"])
    def buscar2():
        nome = request.args.get("nome", "").strip()
        organograma = request.args.get("organograma", "").strip()
        tipo_documento = request.args.get("tipo_documento", "").strip()
        abrangencia = request.args.get("abrangencia", "HUWC").strip()
        apenas_complexo = request.args.get("apenas_complexo", "false") == "true"
        search_organograma = request.args.get("search_organograma", "").strip().lower()

        query = Documento2.query

        if nome:
            termo_busca = normalizar_texto(nome)
            query = query.filter(
                db.func.unaccent(Documento2.nome).ilike(f"%{termo_busca}%")
            )

        if organograma:
            termo_busca = normalizar_texto(organograma)
            query = query.filter(
                or_(
                    db.func.unaccent(Documento2.organograma).ilike(f"%{termo_busca}%"),
                    db.func.unaccent(Documento2.nome_completo).ilike(f"%{termo_busca}%"),
                )
            )

        if tipo_documento:
            termo_busca = normalizar_texto(tipo_documento)
            query = query.filter(
                db.func.unaccent(Documento2.tipo_documento).ilike(f"%{termo_busca}%")
            )

        if abrangencia:
            query = query.filter(Documento2.abrangencia == abrangencia)

        if apenas_complexo:
            query = query.filter(
                or_(
                    Documento2.nome.like("%CH.%"),
                    Documento2.nome.like("%CHUFC.%"),
                )
            )

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
            nome or organograma or tipo_documento or search_organograma or apenas_complexo
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
            db.session.query(Documento2.organograma, Documento2.nome_completo)
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
            "partials/document_list2.html",
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
        abrangencia = request.args.get("abrangencia", "HUWC").strip()

        documentos = Documento2.query.filter_by(
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
