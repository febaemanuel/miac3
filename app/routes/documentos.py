"""Rotas do ciclo de vida de documentos: publicar, visualizar, editar, excluir, versionar."""
import json
import logging
import os
import time
from datetime import datetime

from flask import (
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy.ext.mutable import MutableList
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import Abrangencia, Documento, Organograma, TipoDocumento
from app.services.dates import converter_data, formatar_data_para_input

logger = logging.getLogger(__name__)


def _atualizar_status_documentos():
    """Recalcula campo `atualizado` de cada documento com base no vencimento."""
    documentos = Documento.query.all()
    hoje = datetime.now().date()
    for documento in documentos:
        if documento.vencimento:
            try:
                data_vencimento = converter_data(documento.vencimento)
                documento.atualizado = data_vencimento >= hoje
            except ValueError:
                logger.warning(
                    "Vencimento inválido no doc %s: %r",
                    documento.id, documento.vencimento,
                )
    db.session.commit()


def init_routes(app):
    @app.route("/miac/publicar", methods=["GET"])
    def publicar_page():
        if "username" not in session:
            return redirect(url_for("login"))

        abrangencias = (
            Abrangencia.query.filter_by(ativo=True)
            .order_by(Abrangencia.ordem, Abrangencia.nome)
            .all()
        )
        organogramas = Organograma.query.order_by(Organograma.nome).all()
        tipos_documento = TipoDocumento.query.order_by(TipoDocumento.nome).all()

        organogramas_por_abrangencia = {a.nome: [] for a in abrangencias}
        for org in organogramas:
            if org.abrangencia and org.abrangencia.nome in organogramas_por_abrangencia:
                organogramas_por_abrangencia[org.abrangencia.nome].append(
                    {"sigla": org.nome, "nome_completo": org.nome_completo or ""}
                )

        return render_template(
            "publicar.html",
            abrangencias=[a.nome for a in abrangencias],
            organogramas=[o.nome for o in organogramas],
            organogramas_por_abrangencia=organogramas_por_abrangencia,
            tipos_documento=[t.nome for t in tipos_documento],
        )

    @app.route("/miac/publicar", methods=["POST"])
    def publicar():
        if "username" not in session:
            return jsonify({"error": "Usuário não autenticado"}), 403

        upload_folder = current_app.config["UPLOAD_FOLDER"]

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
                return (
                    jsonify(
                        {
                            "error": "Número de títulos não corresponde ao número de arquivos."
                        }
                    ),
                    400,
                )

            if not (
                len(organogramas)
                == len(tipos_documento)
                == len(abrangencias)
                == len(elaboradores_lista)
                == len(numeros_sei)
                == len(vencimentos)
                == len(datas_elaboracao)
                == len(files)
            ):
                return (
                    jsonify(
                        {
                            "error": "Número de campos não corresponde ao número de arquivos."
                        }
                    ),
                    400,
                )

            log_detalhado = []

            for index, file in enumerate(files):
                filename_lower = file.filename.lower()
                if not (
                    filename_lower.endswith(".pdf")
                    or filename_lower.endswith(".doc")
                    or filename_lower.endswith(".docx")
                ):
                    continue

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

                marcador = None
                documento_existente = Documento.query.filter_by(
                    organograma=organogramas[index],
                    abrangencia=abrangencias[index],
                ).first()
                if documento_existente and documento_existente.marcador:
                    marcador = documento_existente.marcador

                nome_completo = None
                documento_com_nome = Documento.query.filter_by(
                    organograma=organogramas[index]
                ).first()
                if documento_com_nome and documento_com_nome.nome_completo:
                    nome_completo = documento_com_nome.nome_completo

                documento = Documento(
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

        except Exception as exc:
            logger.exception("Erro ao publicar documentos")
            return (
                jsonify({"error": f"Erro ao publicar documentos. Detalhes: {exc}"}),
                500,
            )

    @app.route("/miac/publicados", methods=["GET"])
    def publicados():
        _atualizar_status_documentos()

        abrangencias_ativas = (
            Abrangencia.query.filter_by(ativo=True)
            .order_by(Abrangencia.ordem, Abrangencia.nome)
            .all()
        )
        default_abrang = abrangencias_ativas[0].nome if abrangencias_ativas else ""
        abrangencia_selecionada = request.args.get("abrangencia", default_abrang)
        organograma_filtro = request.args.get("organograma", "").strip()
        tipo_documento_filtro = request.args.get("tipo_documento", "").strip()

        query = Documento.query.filter_by(abrangencia=abrangencia_selecionada)
        if organograma_filtro:
            query = query.filter(Documento.organograma == organograma_filtro)
        if tipo_documento_filtro:
            query = query.filter(Documento.tipo_documento == tipo_documento_filtro)

        documentos = query.all()

        documentos_agrupados = {}
        tipos_documento_unicos = set()
        for documento in documentos:
            marcador = documento.marcador if documento.marcador else "Sem Marcador"
            documentos_agrupados.setdefault(marcador, {})
            documentos_agrupados[marcador].setdefault(documento.organograma, {})
            documentos_agrupados[marcador][documento.organograma].setdefault(
                documento.tipo_documento, []
            )
            documentos_agrupados[marcador][documento.organograma][
                documento.tipo_documento
            ].append(documento)
            if documento.tipo_documento:
                tipos_documento_unicos.add(documento.tipo_documento)

        organogramas_completos = (
            db.session.query(Documento.organograma, Documento.nome_completo)
            .distinct()
            .all()
        )
        organogramas_formatados = [
            {"sigla": org[0], "nome_completo": org[1]} for org in organogramas_completos
        ]
        organogramas_formatados.sort(
            key=lambda x: (x["nome_completo"] or "").lower() or x["sigla"].lower()
        )

        tipos_documento_list = sorted(tipos_documento_unicos)

        return render_template(
            "publicados.html",
            documentos_agrupados=documentos_agrupados,
            organogramas=organogramas_formatados,
            tipos_documento=tipos_documento_list,
            abrangencia_selecionada=abrangencia_selecionada,
            abrangencias=abrangencias_ativas,
            organograma_filtro=organograma_filtro,
            tipo_documento_filtro=tipo_documento_filtro,
        )

    @app.route("/miac/documento/<int:doc_id>", methods=["GET"])
    def documento_detalhes(doc_id):
        documento = db.session.get(Documento, doc_id)
        if documento:
            documento_url = url_for(
                "static",
                filename=f"uploads/{os.path.basename(documento.caminho)}",
                _external=True,
            )
            return render_template(
                "detalhes_documentos.html",
                documento=documento,
                documento_url=documento_url,
                nivel_acesso=session.get("nivel_acesso"),
            )
        return "Documento não encontrado", 404

    @app.route("/miac/excluir_documento/<int:doc_id>", methods=["GET"])
    def excluir_documento(doc_id):
        if "username" not in session:
            return redirect(url_for("login"))

        documento = db.session.get(Documento, doc_id)
        if documento is None:
            return "Documento não encontrado", 404

        db.session.delete(documento)
        db.session.commit()
        flash("Documento excluído com sucesso!", "success")
        return redirect(url_for("publicados"))

    @app.route("/miac/editar_documento/<int:doc_id>", methods=["GET", "POST"])
    def editar_documento(doc_id):
        if "username" not in session or session.get("nivel_acesso") != "elevado":
            return redirect(url_for("login"))

        documento = db.session.get(Documento, doc_id)
        if not documento:
            return "Documento não encontrado", 404

        upload_folder = current_app.config["UPLOAD_FOLDER"]

        if request.method == "POST":
            try:
                documento.nome = request.form.get("nome", documento.nome)
                documento.organograma = request.form.get(
                    "organograma", documento.organograma
                )
                documento.tipo_documento = request.form.get(
                    "tipo_documento", documento.tipo_documento
                )
                documento.abrangencia = request.form.get(
                    "abrangencia", documento.abrangencia
                )
                documento.atualizado = request.form.get("atualizado") == "on"
                documento.data_elaboracao = request.form.get(
                    "data_elaboracao", documento.data_elaboracao
                )
                documento.vencimento = request.form.get(
                    "vencimento", documento.vencimento
                )
                documento.numero_sei = request.form.get(
                    "numero_sei", documento.numero_sei
                )
                documento.elaboradores = request.form.get(
                    "elaboradores", documento.elaboradores
                )

                if (
                    "novo_pdf" in request.files
                    and request.files["novo_pdf"].filename != ""
                ):
                    novo_pdf = request.files["novo_pdf"]
                    if novo_pdf.filename.lower().endswith(".pdf"):
                        if documento.historico_versoes is None:
                            documento.historico_versoes = MutableList()
                        elif not isinstance(documento.historico_versoes, MutableList):
                            documento.historico_versoes = MutableList(
                                documento.historico_versoes
                            )

                        historico_entry = {
                            "versao": documento.versao_efetiva,
                            "caminho": documento.caminho,
                            "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                            "responsavel": session["username"],
                            "nome_arquivo": (
                                os.path.basename(documento.caminho)
                                if documento.caminho
                                else None
                            ),
                        }
                        documento.historico_versoes.append(historico_entry)
                        documento.versao_atual = documento.versao_efetiva + 1

                        file_name = (
                            f"doc_{doc_id}_v{documento.versao_atual}"
                            f"_{int(time.time())}.pdf"
                        )
                        file_path = os.path.join(upload_folder, file_name)
                        novo_pdf.save(file_path)

                        documento.pdf_antigo = documento.caminho
                        documento.caminho = file_path.replace("\\", "/")
                        documento.data_atualizacao = datetime.now()

                db.session.commit()
                flash("Documento atualizado com sucesso!", "success")
                return redirect(url_for("documento_detalhes", doc_id=doc_id))

            except Exception as exc:
                db.session.rollback()
                logger.exception("Erro ao atualizar documento %s", doc_id)
                flash(f"Erro ao atualizar documento: {exc}", "error")
                return redirect(url_for("editar_documento", doc_id=doc_id))

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
        except Exception:
            logger.exception("Erro ao ordenar histórico do doc %s", doc_id)
            historico_ordenado = []

        dados_template = {
            "documento": documento,
            "versao_efetiva": documento.versao_efetiva,
            "historico_efetivo": historico_ordenado,
            "data_elaboracao": formatar_data_para_input(documento.data_elaboracao),
            "vencimento": formatar_data_para_input(documento.vencimento),
        }
        return render_template("editar_documento.html", **dados_template)

    @app.route("/miac/restaurar_versao/<int:doc_id>/<int:versao>", methods=["POST"])
    def restaurar_versao(doc_id, versao):
        if "username" not in session or session.get("nivel_acesso") != "elevado":
            return jsonify({"success": False, "error": "Acesso negado"}), 403

        documento = db.session.get(Documento, doc_id)
        if not documento:
            return jsonify({"success": False, "error": "Documento não encontrado"}), 404

        try:
            historico = (
                documento.historico_versoes
                if documento.historico_versoes is not None
                else []
            )
            versao_restaurar = next(
                (v for v in historico if v["versao"] == versao), None
            )
            if not versao_restaurar:
                return (
                    jsonify(
                        {"success": False, "error": f"Versão {versao} não encontrada"}
                    ),
                    404,
                )

            nova_entrada_historico = {
                "versao": documento.versao_efetiva,
                "caminho": documento.caminho,
                "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "responsavel": session["username"],
                "nome_arquivo": os.path.basename(documento.caminho),
            }
            historico.append(nova_entrada_historico)

            documento.versao_atual = versao
            documento.historico_versoes = [
                v for v in historico if v["versao"] != versao
            ]
            documento.pdf_antigo = documento.caminho
            documento.caminho = versao_restaurar["caminho"]
            documento.data_publicacao = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            db.session.commit()
            return jsonify(
                {"success": True, "message": f"Versão {versao} restaurada com sucesso!"}
            )

        except Exception as exc:
            db.session.rollback()
            return jsonify({"success": False, "error": str(exc)}), 500
