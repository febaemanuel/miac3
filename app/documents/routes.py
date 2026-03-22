"""Document CRUD routes."""
import json
import logging
import os
import time
from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, session, jsonify, send_from_directory,
    flash,
)
from sqlalchemy.ext.mutable import MutableList
from werkzeug.utils import secure_filename

from flask import current_app
from app.decorators import login_required, admin_required
from app.extensions import db
from app.helpers import (
    get_organogramas_formatados, calcular_stats_dashboard,
    agrupar_documentos,
)
from app.models import Documento, Documento2
from app.utils import (
    verificar_vencimentos, atualizar_status_documentos,
    formatar_data_para_input,
)

documents_bp = Blueprint("documents", __name__, url_prefix="/miac")
logger = logging.getLogger(__name__)


@documents_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    stats = calcular_stats_dashboard()
    notificacoes = verificar_vencimentos()
    return render_template("index.html", stats=stats, notificacoes=notificacoes)


@documents_bp.route("/lista")
@login_required
def lista():
    return render_template("lista.html")


@documents_bp.route("/relacao")
@login_required
def relacao():
    documentos = Documento.query.all()
    return render_template("relacao.html", documentos=documentos)


@documents_bp.route("/relacao_documentos")
@login_required
def relacao_documentos():
    documentos = Documento2.query.all()
    return render_template("relacao_documentos.html", documentos=documentos)


@documents_bp.route("/publicados", methods=["GET"])
@login_required
def publicados():
    documentos = Documento.query.all()
    return render_template("publicados.html", documentos=documentos)


@documents_bp.route("/publicados2", methods=["GET"])
@login_required
def publicados2():
    atualizar_status_documentos()

    abrangencia_selecionada = request.args.get("abrangencia", "HUWC")
    organograma_filtro = request.args.get("organograma", "").strip()
    tipo_documento_filtro = request.args.get("tipo_documento", "").strip()

    query = Documento2.query.filter_by(abrangencia=abrangencia_selecionada)

    if organograma_filtro:
        query = query.filter(Documento2.organograma == organograma_filtro)
    if tipo_documento_filtro:
        query = query.filter(Documento2.tipo_documento == tipo_documento_filtro)

    documentos = query.all()
    documentos_agrupados = agrupar_documentos(documentos)
    tipos_documento = sorted(
        {doc.tipo_documento for doc in documentos if doc.tipo_documento}
    )
    stats_rapidas = calcular_stats_dashboard(abrangencia=abrangencia_selecionada)

    return render_template(
        "publicados2.html",
        documentos_agrupados=documentos_agrupados,
        organogramas=get_organogramas_formatados(),
        tipos_documento=tipos_documento,
        abrangencia_selecionada=abrangencia_selecionada,
        organograma_filtro=organograma_filtro,
        tipo_documento_filtro=tipo_documento_filtro,
        stats_rapidas=stats_rapidas,
    )


@documents_bp.route("/documento/<int:doc_id>", methods=["GET"])
@login_required
def documento_detalhes(doc_id):
    documento = db.session.get(Documento, doc_id)
    if documento:
        documento_url = url_for(
            "static",
            filename=f"uploads2/{os.path.basename(documento.caminho)}",
            _external=True,
        )
        return render_template(
            "detalhes_documento.html",
            documento=documento,
            documento_url=documento_url,
        )
    else:
        return "Documento não encontrado", 404


@documents_bp.route("/documento2/<int:doc_id>", methods=["GET"])
@login_required
def documento2_detalhes(doc_id):
    documento = db.session.get(Documento2, doc_id)
    if documento:
        documento_url = url_for(
            "static",
            filename=f"uploads2/{os.path.basename(documento.caminho)}",
            _external=True,
        )
        return render_template(
            "detalhes2_documentos.html",
            documento=documento,
            documento_url=documento_url,
            nivel_acesso=session.get("nivel_acesso"),
        )
    else:
        return "Documento não encontrado", 404


@documents_bp.route("/publicar2", methods=["GET"])
@login_required
def publicar2_page():
    organogramas = db.session.query(Documento2.organograma).distinct().all()
    tipos_documento = db.session.query(Documento2.tipo_documento).distinct().all()
    abrangencias = db.session.query(Documento2.abrangencia).distinct().all()

    return render_template(
        "publicar2.html",
        organogramas=[org[0] for org in organogramas if org[0]],
        tipos_documento=[tipo[0] for tipo in tipos_documento if tipo[0]],
        abrangencias=[abrang[0] for abrang in abrangencias if abrang[0]],
    )


@documents_bp.route("/publicar2", methods=["POST"])
@login_required
def publicar2():
    try:
        files = request.files.getlist("pdf_file")
        titulos = request.form.getlist("titulo[]")
        organogramas = request.form.getlist("organograma[]")
        tipos_documento = request.form.getlist("tipo_documento[]")
        abrangencias = request.form.getlist("abrangencia[]")
        elaboradores_lista = request.form.getlist("elaboradores[]")
        numeros_sei = request.form.getlist("numero_sei[]")
        vencimentos = request.form.getlist("vencimento[]")
        datas_elaboracao = request.form.getlist("data_elaboracao[]")

        if len(titulos) != len(files):
            return jsonify(
                {"error": "Número de títulos não corresponde ao número de arquivos."}
            ), 400

        if not (
            len(organogramas) == len(tipos_documento) == len(abrangencias)
            == len(elaboradores_lista) == len(numeros_sei)
            == len(vencimentos) == len(datas_elaboracao) == len(files)
        ):
            return jsonify(
                {"error": "Número de campos não corresponde ao número de arquivos."}
            ), 400

        upload_folder = current_app.config["UPLOAD_FOLDER"]
        max_file_size = current_app.config["MAX_FILE_SIZE"]
        allowed_extensions = current_app.config["ALLOWED_EXTENSIONS"]
        log_detalhado = []

        for index, file in enumerate(files):
            filename_lower = file.filename.lower()
            ext = os.path.splitext(filename_lower)[1]

            if ext not in allowed_extensions:
                continue

            file.seek(0, 2)
            file_size = file.tell()
            file.seek(0)
            if file_size > max_file_size:
                return jsonify(
                    {"error": f"Arquivo '{file.filename}' excede o limite de 50 MB."}
                ), 400

            base_nome = secure_filename(titulos[index].replace(" ", "_"))
            file_ext = os.path.splitext(file.filename)[1].lower()
            file_name = f"{base_nome}_{int(time.time())}{file_ext}"
            file_path = os.path.join(upload_folder, file_name).replace("\\", "/")

            contador = 1
            while os.path.exists(file_path):
                file_name = f"{base_nome}_{int(time.time())}_v{contador}{file_ext}"
                file_path = os.path.join(upload_folder, file_name).replace("\\", "/")
                contador += 1

            file.save(file_path)

            # Inherit marcador from existing document with same organograma+abrangencia
            marcador = None
            doc_existente = Documento2.query.filter_by(
                organograma=organogramas[index],
                abrangencia=abrangencias[index],
            ).first()
            if doc_existente and doc_existente.marcador:
                marcador = doc_existente.marcador

            # Inherit nome_completo from existing document with same organograma
            nome_completo = None
            doc_com_nome = Documento2.query.filter_by(
                organograma=organogramas[index]
            ).first()
            if doc_com_nome and doc_com_nome.nome_completo:
                nome_completo = doc_com_nome.nome_completo

            documento = Documento2(
                nome=titulos[index],
                organograma=organogramas[index],
                tipo_documento=tipos_documento[index],
                abrangencia=abrangencias[index],
                atualizado=True,
                data_elaboracao=datas_elaboracao[index],
                vencimento=vencimentos[index],
                numero_sei=numeros_sei[index],
                elaboradores=elaboradores_lista[index],
                caminho=file_path,
                data_publicacao=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                marcador=marcador,
                nome_completo=nome_completo,
            )
            db.session.add(documento)
            log_detalhado.append(f"{titulos[index]} salvo como {file_name}")

        db.session.commit()

        for log in log_detalhado:
            logger.info("Publicação: %s", log)

        return jsonify({"message": "Documentos publicados com sucesso!"})

    except Exception as e:
        logger.exception("Erro ao publicar documentos")
        return jsonify(
            {"error": f"Erro ao publicar documentos. Detalhes: {str(e)}"}
        ), 500


@documents_bp.route("/editar_documento2/<int:doc_id>", methods=["GET", "POST"])
@admin_required
def editar_documento2(doc_id):
    documento = db.session.get(Documento2, doc_id)
    if not documento:
        return "Documento não encontrado", 404

    upload_folder = current_app.config["UPLOAD_FOLDER"]

    if request.method == "POST":
        try:
            documento.nome = request.form.get("nome", documento.nome)
            documento.organograma = request.form.get("organograma", documento.organograma)
            documento.tipo_documento = request.form.get("tipo_documento", documento.tipo_documento)
            documento.abrangencia = request.form.get("abrangencia", documento.abrangencia)
            documento.atualizado = request.form.get("atualizado") == "on"
            documento.data_elaboracao = request.form.get("data_elaboracao", documento.data_elaboracao)
            documento.vencimento = request.form.get("vencimento", documento.vencimento)
            documento.numero_sei = request.form.get("numero_sei", documento.numero_sei)
            documento.elaboradores = request.form.get("elaboradores", documento.elaboradores)

            if "novo_pdf" in request.files and request.files["novo_pdf"].filename != "":
                novo_pdf = request.files["novo_pdf"]

                if novo_pdf.filename.lower().endswith(".pdf"):
                    if documento.historico_versoes is None:
                        documento.historico_versoes = MutableList()
                    elif not isinstance(documento.historico_versoes, MutableList):
                        documento.historico_versoes = MutableList(documento.historico_versoes)

                    historico_entry = {
                        "versao": documento.versao_atual if documento.versao_atual is not None else 1,
                        "caminho": documento.caminho,
                        "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                        "responsavel": session["username"],
                        "nome_arquivo": os.path.basename(documento.caminho) if documento.caminho else None,
                    }

                    documento.historico_versoes.append(historico_entry)
                    documento.versao_atual = (documento.versao_atual or 1) + 1

                    file_name = f"doc_{doc_id}_v{documento.versao_atual}_{int(time.time())}.pdf"
                    file_path = os.path.join(upload_folder, file_name)
                    novo_pdf.save(file_path)
                    logger.info("Novo PDF do documento %d salvo em %s", doc_id, file_path)

                    documento.pdf_antigo = documento.caminho
                    documento.caminho = file_path.replace("\\", "/")
                    documento.data_atualizacao = datetime.now()

            db.session.commit()
            flash("Documento atualizado com sucesso!", "success")
            return redirect(url_for("documents.documento2_detalhes", doc_id=doc_id))

        except Exception as e:
            db.session.rollback()
            logger.exception("Erro ao atualizar documento %d", doc_id)
            flash(f"Erro ao atualizar documento: {str(e)}", "error")
            return redirect(url_for("documents.editar_documento2", doc_id=doc_id))

    # GET request - prepare template data
    historico = []
    if documento.historico_versoes:
        if isinstance(documento.historico_versoes, (MutableList, list)):
            historico = list(documento.historico_versoes)
        elif isinstance(documento.historico_versoes, str):
            try:
                historico = json.loads(documento.historico_versoes)
            except json.JSONDecodeError:
                historico = []

    try:
        historico_ordenado = sorted(
            [h for h in historico if isinstance(h, dict) and "versao" in h],
            key=lambda x: x["versao"],
            reverse=True,
        )
    except Exception as e:
        logger.warning("Erro ao ordenar histórico do documento %d: %s", doc_id, e)
        historico_ordenado = []

    return render_template(
        "editar_documento2.html",
        documento=documento,
        versao_efetiva=documento.versao_atual if documento.versao_atual is not None else 1,
        historico_efetivo=historico_ordenado,
        data_elaboracao=formatar_data_para_input(documento.data_elaboracao),
        vencimento=formatar_data_para_input(documento.vencimento),
    )


@documents_bp.route("/restaurar_versao/<int:doc_id>/<int:versao>", methods=["POST"])
@admin_required
def restaurar_versao(doc_id, versao):
    documento = db.session.get(Documento2, doc_id)
    if not documento:
        return jsonify({"success": False, "error": "Documento não encontrado"}), 404

    try:
        historico = documento.historico_versoes if documento.historico_versoes is not None else []
        versao_restaurar = next((v for v in historico if v["versao"] == versao), None)

        if not versao_restaurar:
            return jsonify(
                {"success": False, "error": f"Versão {versao} não encontrada"}
            ), 404

        nova_entrada_historico = {
            "versao": documento.versao_atual if documento.versao_atual is not None else 1,
            "caminho": documento.caminho,
            "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "responsavel": session["username"],
            "nome_arquivo": os.path.basename(documento.caminho),
        }
        historico.append(nova_entrada_historico)

        documento.versao_atual = versao
        documento.historico_versoes = [v for v in historico if v["versao"] != versao]
        documento.pdf_antigo = documento.caminho
        documento.caminho = versao_restaurar["caminho"]
        documento.data_publicacao = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        db.session.commit()
        return jsonify(
            {"success": True, "message": f"Versão {versao} restaurada com sucesso!"}
        )

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@documents_bp.route("/excluir_documento/<int:doc_id>/<tipo>", methods=["POST"])
@admin_required
def excluir_documento(doc_id, tipo):
    if tipo == "documento":
        documento = db.session.get(Documento, doc_id)
    elif tipo == "documento2":
        documento = db.session.get(Documento2, doc_id)
    else:
        return "Tipo de documento inválido", 400

    if documento is None:
        return "Documento não encontrado", 404

    db.session.delete(documento)
    db.session.commit()
    flash("Documento excluído com sucesso!", "success")

    if tipo == "documento":
        return redirect(url_for("documents.publicados"))
    else:
        return redirect(url_for("documents.publicados2"))


@documents_bp.route("/excluir_documento2/<int:doc_id>", methods=["POST"])
@admin_required
def excluir_documento2(doc_id):
    documento = db.session.get(Documento2, doc_id)
    if not documento:
        return jsonify({"error": "Documento não encontrado"}), 404

    try:
        for caminho in [documento.caminho, documento.pdf_antigo]:
            if caminho and os.path.exists(caminho):
                try:
                    os.remove(caminho)
                except Exception:
                    pass

        db.session.delete(documento)
        db.session.commit()
        flash("Documento excluído com sucesso!", "success")
        return redirect(url_for("documents.publicados2"))
    except Exception as e:
        db.session.rollback()
        logger.exception("Erro ao excluir documento %d", doc_id)
        flash(f"Erro ao excluir: {str(e)}", "error")
        return redirect(url_for("documents.documento2_detalhes", doc_id=doc_id))


@documents_bp.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)
