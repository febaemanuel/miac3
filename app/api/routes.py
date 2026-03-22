"""API and search routes."""
import csv
import io
import logging
import os
import time
from datetime import datetime

from flask import (
    Blueprint, render_template, request, jsonify,
    session, Response,
)
from sqlalchemy import or_
from werkzeug.utils import secure_filename

from flask import current_app
from app.decorators import login_required
from app.extensions import db
from app.helpers import (
    get_organogramas_formatados, calcular_stats_dashboard,
    agrupar_documentos, aplicar_filtros_query,
)
from app.models import Documento, Documento2
from app.utils import (
    normalizar_texto, parse_data, read_last_page,
    send_to_deepseek_with_retry, send_to_gpt_with_retry,
)

api_bp = Blueprint("api", __name__, url_prefix="/miac")
logger = logging.getLogger(__name__)


@api_bp.route("/api/stats")
@login_required
def stats():
    abrangencia = request.args.get("abrangencia", "").strip()
    stats = calcular_stats_dashboard(
        abrangencia=abrangencia if abrangencia else None
    )
    return jsonify(stats)


@api_bp.route("/api/vencendo")
@login_required
def vencendo():
    """Returns documents expiring within N days."""
    dias = int(request.args.get("dias", 30))
    abrangencia = request.args.get("abrangencia", "").strip()
    hoje = datetime.now()

    query = Documento2.query.filter_by(atualizado=True)
    if abrangencia:
        query = query.filter_by(abrangencia=abrangencia)

    docs = query.all()
    resultado = []
    for doc in docs:
        if doc.vencimento:
            try:
                dt = parse_data(doc.vencimento)
                diff = (dt - hoje).days
                if 0 <= diff <= dias:
                    resultado.append({
                        "id": doc.id,
                        "nome": doc.nome,
                        "organograma": doc.organograma,
                        "abrangencia": doc.abrangencia,
                        "vencimento": doc.vencimento,
                        "dias_restantes": diff,
                    })
            except ValueError:
                pass

    resultado.sort(key=lambda x: x["dias_restantes"])
    return jsonify(resultado)


@api_bp.route("/buscar", methods=["GET"])
@login_required
def buscar():
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


@api_bp.route("/buscar2", methods=["GET"])
@login_required
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
        query = query.filter(or_(
            db.func.unaccent(Documento2.organograma).ilike(f"%{termo_busca}%"),
            db.func.unaccent(Documento2.nome_completo).ilike(f"%{termo_busca}%"),
        ))

    if tipo_documento:
        termo_busca = normalizar_texto(tipo_documento)
        query = query.filter(
            db.func.unaccent(Documento2.tipo_documento).ilike(f"%{termo_busca}%")
        )

    if abrangencia:
        query = query.filter(Documento2.abrangencia == abrangencia)

    if apenas_complexo:
        query = query.filter(or_(
            Documento2.nome.like("%CH.%"),
            Documento2.nome.like("%CHUFC.%"),
        ))

    documentos = query.all()

    if search_organograma:
        documentos = [
            doc for doc in documentos
            if (search_organograma in normalizar_texto(doc.organograma)
                or (doc.nome_completo and search_organograma in normalizar_texto(doc.nome_completo)))
        ]

    tem_filtro = bool(nome or organograma or tipo_documento or search_organograma or apenas_complexo)
    documentos_agrupados = {} if tem_filtro else agrupar_documentos(documentos)
    tipos_documento = sorted(
        {doc.tipo_documento for doc in documentos if doc.tipo_documento}
    )

    return render_template(
        "partials/document_list2.html",
        documentos_agrupados=documentos_agrupados,
        documentos=documentos,
        exibir_lista=tem_filtro,
        abrangencia=abrangencia,
        organogramas=get_organogramas_formatados(),
        tipos_documento=tipos_documento,
        organograma_filtro=organograma,
        tipo_documento_filtro=tipo_documento,
    )


@api_bp.route("/carregar_documentos_modal", methods=["GET"])
@login_required
def carregar_documentos_modal():
    organograma = request.args.get("organograma", "").strip()
    abrangencia = request.args.get("abrangencia", "HUWC").strip()

    documentos = Documento2.query.filter_by(
        organograma=organograma, abrangencia=abrangencia
    ).all()

    documentos_por_tipo = {}
    for doc in documentos:
        if doc.tipo_documento not in documentos_por_tipo:
            documentos_por_tipo[doc.tipo_documento] = []
        documentos_por_tipo[doc.tipo_documento].append(doc)

    return render_template(
        "partials/modal_content.html",
        organograma=organograma,
        documentos_por_tipo=documentos_por_tipo,
    )


@api_bp.route("/obter-dados", methods=["POST"])
@login_required
def obter_dados():
    try:
        files = request.files.getlist("pdf_file")
        modelo_ia = request.form.get("modelo_ia", "deepseek")

        if not files:
            return jsonify({"error": "Nenhum arquivo enviado."}), 400

        upload_folder = current_app.config["UPLOAD_FOLDER"]
        deepseek_key = current_app.config["DEEPSEEK_API_KEY"]
        chatgpt_key = current_app.config["CHATGPT_API_KEY"]

        resultados = []
        for file in files:
            if file.filename == "" or not file.filename.lower().endswith(".pdf"):
                continue

            tentativa = 0
            sucesso = False
            file_path = None

            while tentativa < 3 and not sucesso:
                try:
                    file_name = f"{int(time.time())}_{secure_filename(file.filename)}"
                    file_path = os.path.join(upload_folder, file_name).replace("\\", "/")
                    file.save(file_path)

                    pdf_text = read_last_page(file_path)

                    if pdf_text is None or len(pdf_text.strip()) < 20:
                        raise Exception(
                            f"Texto não encontrado ou insuficiente no PDF: {file.filename}"
                        )

                    prompt = (
                        f"Por favor, extraia as seguintes informações do texto de forma literal. "
                        f"Retorne apenas o valor encontrado ou 'Não localizado' se não houver correspondência. "
                        f"Não use alternativas aproximadas.\n"
                        f"Data de Elaboração (tem que ser no formato dd/mm/aaaa se encontrar dd.mm.aaaa mande no formato que eu disse:\n"
                        f"Vencimento (também pode ser identificado como 'Revisão' mande nesse formato dd/mm/aaaa sempre mesmo se tiver no formato dd.mm.aaaa, pq as vezes voce pode achar dd.mm.aaaa, se não achar, a data de vencimento é 2 a mais do que a de elaboração aaaa+2):\n"
                        f"Organograma (se o formato for EX:'POP.UAP-CHUFC.006', 'UAP' é o Organograma. "
                        f"Se o formato for EX 'PRO.MED-OBS-MEAC.013', 'MED-OBS' é o Organograma. "
                        f"Caso o código do documento seja EX'FOR.DIVGP-CHUFC.005', 'DIVGP' é o Organograma. "
                        f"Os outros códigos serão parecidos com esse, entendeu? Serão nesse formato, códigos genéricos):\n"
                        f"Tipo de Documento (RETORNE EM CAIXA ALTA, se aparer FOR é FORMULÁRIO, SE APARECER POP É PROCEDIMENTO OPERACIONAL PADRÃO, MANDE COMPLETO):\n"
                        f"Abrangência (se a sigla final for 'CHUFC' ou 'CH', retorne 'HUWC'. "
                        f"Se for 'MEAC' ou 'HUWC', mantenha a sigla encontrada, ou seja, no final só pode ser MEAC ou HUWC):\n"
                        f"Código do Documento (ex.: 'FOR.DIVGP-CHUFC.005'):\n"
                        f"Título do Documento:\n"
                        f"Número SEI (é tipo esse o SEI nº 23533.003368/2023-10):\n"
                        f"Elaboradores (separe por vírgula caso tenha mais de um):\n"
                        f"Texto:\n{pdf_text}"
                    )

                    if modelo_ia == "deepseek":
                        gpt_response = send_to_deepseek_with_retry(prompt, deepseek_key)
                    elif modelo_ia == "chatgpt":
                        gpt_response = send_to_gpt_with_retry(prompt, chatgpt_key)
                    else:
                        return jsonify({"error": "Modelo de IA inválido"}), 400

                    if gpt_response is None:
                        raise Exception(
                            f"Erro ao comunicar com a API de IA para o arquivo: {file.filename}"
                        )

                    lines = [line.strip() for line in gpt_response.split("\n") if line.strip()]

                    extracted_data = {
                        "data_elaboracao": "Não localizado",
                        "vencimento": "Não localizado",
                        "numero_sei": "Não localizado",
                        "organograma": "Não localizado",
                        "tipo_documento": "Não localizado",
                        "abrangencia": "Não localizado",
                        "codigo_documento": "Não localizado",
                        "titulo_documento": file.filename,
                        "elaboradores": "Não localizado",
                    }

                    for line in lines:
                        if "Data de Elaboração:" in line:
                            extracted_data["data_elaboracao"] = line.split(":", 1)[1].strip()
                        elif "Vencimento:" in line or "Revisão:" in line:
                            extracted_data["vencimento"] = line.split(":", 1)[1].strip()
                        elif "Número SEI:" in line:
                            extracted_data["numero_sei"] = line.split(":", 1)[1].strip()
                        elif "Organograma:" in line:
                            extracted_data["organograma"] = line.split(":", 1)[1].strip()
                        elif "Tipo de Documento:" in line:
                            extracted_data["tipo_documento"] = line.split(":", 1)[1].strip()
                        elif "Abrangência:" in line:
                            extracted_data["abrangencia"] = line.split(":", 1)[1].strip()
                        elif "Código do Documento:" in line:
                            extracted_data["codigo_documento"] = line.split(":", 1)[1].strip()
                        elif "Título do Documento:" in line:
                            extracted_data["titulo_documento"] = line.split(":", 1)[1].strip()
                        elif "Elaboradores:" in line:
                            elaboradores = line.split(":", 1)[1].strip()
                            extracted_data["elaboradores"] = [
                                e.strip() for e in elaboradores.split(",")
                            ]

                    titulo_completo = (
                        f"{extracted_data['codigo_documento']} - {extracted_data['titulo_documento']}"
                        if (extracted_data["codigo_documento"] != "Não localizado"
                            and extracted_data["titulo_documento"] != file.filename)
                        else file.filename
                    )

                    resultados.append({
                        "gpt_response": {
                            "data_elaboracao": extracted_data["data_elaboracao"],
                            "vencimento": extracted_data["vencimento"],
                            "numero_sei": extracted_data["numero_sei"],
                            "titulo": titulo_completo,
                            "organograma": extracted_data["organograma"],
                            "tipo_documento": extracted_data["tipo_documento"],
                            "abrangencia": extracted_data["abrangencia"],
                            "texto_extraido": (
                                pdf_text[:200] + "..." if len(pdf_text) > 200 else pdf_text
                            ),
                        },
                        "elaboradores": (
                            extracted_data["elaboradores"]
                            if isinstance(extracted_data["elaboradores"], list)
                            else [extracted_data["elaboradores"]]
                        ),
                        "status": "sucesso",
                    })

                    sucesso = True

                except Exception as e:
                    tentativa += 1
                    if tentativa == 3:
                        resultados.append({
                            "titulo": file.filename,
                            "status": f"Erro após 3 tentativas: {str(e)}",
                            "texto_extraido": (
                                pdf_text[:200] + "..."
                                if pdf_text and len(pdf_text) > 200
                                else (pdf_text if pdf_text else "Nenhum texto extraído")
                            ),
                        })
                    time.sleep(1)

                finally:
                    if file_path and os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except Exception as e:
                            logger.warning("Erro ao remover arquivo temporário: %s", e)

        return jsonify(resultados)

    except Exception as e:
        logger.exception("Erro ao processar arquivos")
        return jsonify({"error": f"Erro ao processar arquivos: {str(e)}"}), 500


@api_bp.route("/exportar_csv")
@login_required
def exportar_csv():
    abrangencia = request.args.get("abrangencia", "").strip()
    organograma = request.args.get("organograma", "").strip()
    tipo_documento = request.args.get("tipo_documento", "").strip()
    status = request.args.get("status", "").strip()

    query = Documento2.query
    query = aplicar_filtros_query(
        query,
        abrangencia=abrangencia,
        organograma=organograma,
        tipo_documento=tipo_documento,
        status=status,
    )

    documentos = query.order_by(Documento2.organograma, Documento2.nome).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Nome", "Organograma", "Tipo de Documento", "Abrangência",
        "Data de Elaboração", "Vencimento", "Número SEI", "Elaboradores",
        "Atualizado", "Marcador", "Data de Publicação", "Versão Atual",
    ])

    for doc in documentos:
        status_doc = "Atualizado" if doc.atualizado else "Vencido"
        writer.writerow([
            doc.id,
            doc.nome or "",
            doc.organograma or "",
            doc.tipo_documento or "",
            doc.abrangencia or "",
            doc.data_elaboracao or "",
            doc.vencimento or "",
            doc.numero_sei or "",
            doc.elaboradores or "",
            status_doc,
            doc.marcador or "",
            doc.data_publicacao or "",
            doc.versao_atual or 1,
        ])

    output.seek(0)
    hoje = datetime.now()
    filename = f"documentos_miac_{hoje.strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
