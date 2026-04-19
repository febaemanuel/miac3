"""API interna: endpoint AJAX de extração de metadados via IA."""
import os
import time
import traceback

from flask import current_app, jsonify, request, session
from werkzeug.utils import secure_filename

from app.services.ia_service import (
    send_to_deepseek_with_retry,
    send_to_gpt_with_retry,
)
from app.services.pdf_service import read_last_page


PROMPT_EXTRACAO = (
    "Por favor, extraia as seguintes informações do texto de forma literal. "
    "Retorne apenas o valor encontrado ou 'Não localizado' se não houver correspondência. "
    "Não use alternativas aproximadas.\n"
    "Data de Elaboração (tem que ser no formato dd/mm/aaaa se encontrar dd.mm.aaaa "
    "mande no formato que eu disse:\n"
    "Vencimento (também pode ser identificado como 'Revisão' mande nesse formato "
    "dd/mm/aaaa sempre mesmo se tiver no formato dd.mm.aaaa, pq as vezes voce pode "
    "achar dd.mm.aaaa, se não achar, a data de vencimento é 2 a mais do que a de "
    "elaboração aaaa+2):\n"
    "Organograma (se o formato for EX:'POP.UAP-CHUFC.006', 'UAP' é o Organograma. "
    "Se o formato for EX 'PRO.MED-OBS-MEAC.013', 'MED-OBS' é o Organograma. "
    "Caso o código do documento seja EX'FOR.DIVGP-CHUFC.005', 'DIVGP' é o Organograma. "
    "Os outros códigos serão parecidos com esse, entendeu? Serão nesse formato, códigos "
    "genéricos):\n"
    "Tipo de Documento (RETORNE EM CAIXA ALTA, se aparer FOR é FORMULÁRIO, SE APARECER "
    "POP É PROCEDIMENTO OPERACIONAL PADRÃO, MANDE COMPLETO):\n"
    "Abrangência (se a sigla final for 'CHUFC' ou 'CH', retorne 'HUWC'. "
    "Se for 'MEAC' ou 'HUWC', mantenha a sigla encontrada, ou seja, no final só pode "
    "ser MEAC ou HUWC):\n"
    "Código do Documento (ex.: 'FOR.DIVGP-CHUFC.005'):\n"
    "Título do Documento:\n"
    "Número SEI (é tipo esse o SEI nº 23533.003368/2023-10):\n"
    "Elaboradores (separe por vírgula caso tenha mais de um):\n"
    "Texto:\n"
)


def _parse_gpt_response(response_text, filename):
    extracted = {
        "data_elaboracao": "Não localizado",
        "vencimento": "Não localizado",
        "numero_sei": "Não localizado",
        "organograma": "Não localizado",
        "tipo_documento": "Não localizado",
        "abrangencia": "Não localizado",
        "codigo_documento": "Não localizado",
        "titulo_documento": filename,
        "elaboradores": "Não localizado",
    }
    campos = {
        "Data de Elaboração:": "data_elaboracao",
        "Número SEI:": "numero_sei",
        "Organograma:": "organograma",
        "Tipo de Documento:": "tipo_documento",
        "Abrangência:": "abrangencia",
        "Código do Documento:": "codigo_documento",
        "Título do Documento:": "titulo_documento",
    }
    for line in (ln.strip() for ln in response_text.split("\n") if ln.strip()):
        matched = False
        for prefixo, chave in campos.items():
            if prefixo in line:
                extracted[chave] = line.split(":", 1)[1].strip()
                matched = True
                break
        if matched:
            continue
        if "Vencimento:" in line or "Revisão:" in line:
            extracted["vencimento"] = line.split(":", 1)[1].strip()
        elif "Elaboradores:" in line:
            elaboradores = line.split(":", 1)[1].strip()
            extracted["elaboradores"] = [e.strip() for e in elaboradores.split(",")]
    return extracted


def init_routes(app):
    @app.route("/miac/obter-dados", methods=["POST"])
    def obter_dados():
        if "username" not in session:
            return jsonify({"error": "Usuário não autenticado"}), 403

        upload_folder = current_app.config["UPLOAD_FOLDER"]
        deepseek_key = current_app.config["DEEPSEEK_API_KEY"]
        openai_key = current_app.config["OPENAI_API_KEY"]

        try:
            files = request.files.getlist("pdf_file")
            modelo_ia = request.form.get("modelo_ia", "deepseek")
            if not files:
                return jsonify({"error": "Nenhum arquivo enviado."}), 400

            resultados = []
            for file in files:
                if file.filename == "" or not file.filename.lower().endswith(".pdf"):
                    continue

                tentativa = 0
                sucesso = False
                file_path = None
                pdf_text = None

                while tentativa < 3 and not sucesso:
                    try:
                        file_name = (
                            f"{int(time.time())}_{secure_filename(file.filename)}"
                        )
                        file_path = os.path.join(upload_folder, file_name).replace(
                            "\\", "/"
                        )
                        file.save(file_path)

                        pdf_text = read_last_page(file_path)
                        if pdf_text is None or len(pdf_text.strip()) < 20:
                            raise RuntimeError(
                                f"Texto não encontrado ou insuficiente no PDF: {file.filename}"
                            )

                        prompt = PROMPT_EXTRACAO + pdf_text
                        if modelo_ia == "deepseek":
                            gpt_response = send_to_deepseek_with_retry(
                                prompt, deepseek_key
                            )
                        elif modelo_ia == "chatgpt":
                            gpt_response = send_to_gpt_with_retry(prompt, openai_key)
                        else:
                            return jsonify({"error": "Modelo de IA inválido"}), 400

                        if gpt_response is None:
                            raise RuntimeError(
                                f"Erro ao comunicar com a API de IA para: {file.filename}"
                            )

                        extracted = _parse_gpt_response(gpt_response, file.filename)
                        titulo_completo = (
                            f"{extracted['codigo_documento']} - "
                            f"{extracted['titulo_documento']}"
                            if (
                                extracted["codigo_documento"] != "Não localizado"
                                and extracted["titulo_documento"] != file.filename
                            )
                            else file.filename
                        )

                        elaboradores = extracted["elaboradores"]
                        if not isinstance(elaboradores, list):
                            elaboradores = [elaboradores]

                        resultados.append(
                            {
                                "gpt_response": {
                                    "data_elaboracao": extracted["data_elaboracao"],
                                    "vencimento": extracted["vencimento"],
                                    "numero_sei": extracted["numero_sei"],
                                    "titulo": titulo_completo,
                                    "organograma": extracted["organograma"],
                                    "tipo_documento": extracted["tipo_documento"],
                                    "abrangencia": extracted["abrangencia"],
                                    "texto_extraido": (
                                        pdf_text[:200] + "..."
                                        if len(pdf_text) > 200
                                        else pdf_text
                                    ),
                                },
                                "elaboradores": elaboradores,
                                "status": "sucesso",
                            }
                        )
                        sucesso = True

                    except Exception as exc:
                        tentativa += 1
                        if tentativa == 3:
                            texto_preview = (
                                pdf_text[:200] + "..."
                                if pdf_text and len(pdf_text) > 200
                                else (pdf_text or "Nenhum texto extraído")
                            )
                            resultados.append(
                                {
                                    "titulo": file.filename,
                                    "status": f"Erro após 3 tentativas: {exc}",
                                    "texto_extraido": texto_preview,
                                }
                            )
                        time.sleep(1)
                    finally:
                        if file_path and os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                            except Exception as exc:
                                print(f"Erro ao remover arquivo temporário: {exc}")

            return jsonify(resultados)

        except Exception as exc:
            traceback.print_exc()
            return jsonify({"error": f"Erro ao processar arquivos: {exc}"}), 500
