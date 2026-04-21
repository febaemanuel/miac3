"""API interna: endpoint AJAX de extração de metadados via IA."""
import logging
import os
import time

from flask import current_app, jsonify, request, session
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

from app.models import CampoExtracao, IaConfig
from app.services.ia_service import (
    send_to_deepseek_with_retry,
    send_to_gpt_with_retry,
)
from app.services.pdf_service import read_last_page
from app.services.vocabulario import (
    listar_abrangencias,
    listar_organogramas,
    listar_tipos_documento,
    resolver_abrangencia,
    resolver_organograma,
    resolver_tipo_documento,
)


PROMPT_PADRAO = (
    "Extraia as seguintes informações do texto de forma literal. "
    "Retorne apenas o valor encontrado ou 'Não localizado' se não houver correspondência. "
    "Não use alternativas aproximadas.\n"
    "{campos_fixos}"
    "{campos_extras}"
    "\nTexto:\n{texto_pdf}"
)


def _campos_fixos_instrucoes():
    abrangencias = listar_abrangencias()
    organogramas = listar_organogramas()
    tipos = listar_tipos_documento()

    def _ou_livre(lista):
        return (
            f"OBRIGATORIAMENTE um destes: {', '.join(lista)}"
            if lista
            else "valor livre"
        )

    return (
        "Data de Elaboração (formato dd/mm/aaaa):\n"
        "Vencimento (também pode ser 'Revisão'; formato dd/mm/aaaa; "
        "se não houver, use data de elaboração + 2 anos):\n"
        f"Organograma ({_ou_livre(organogramas)}; em códigos tipo 'POP.UAP-CHUFC.006' é a sigla do meio, ex.: 'UAP'):\n"
        f"Tipo de Documento ({_ou_livre(tipos)}; retorne em CAIXA ALTA):\n"
        f"Abrangência ({_ou_livre(abrangencias)}):\n"
        "Código do Documento (ex.: 'FOR.DIVGP-CHUFC.005'):\n"
        "Título do Documento:\n"
        "Número SEI (ex.: 23533.003368/2023-10):\n"
        "Elaboradores (separe por vírgula se mais de um):\n"
    )


def _campos_extras_instrucoes(campos):
    if not campos:
        return ""
    linhas = []
    for c in campos:
        instrucao = f" ({c.instrucao_ia})" if c.instrucao_ia else ""
        linhas.append(f"{c.rotulo}{instrucao}:\n")
    return "".join(linhas)


def _build_prompt(pdf_text, campos_extras):
    config = IaConfig.get()
    template = config.prompt_extracao or PROMPT_PADRAO
    return template.format(
        campos_fixos=_campos_fixos_instrucoes(),
        campos_extras=_campos_extras_instrucoes(campos_extras),
        texto_pdf=pdf_text,
    )


def _parse_gpt_response(response_text, filename, campos_extras):
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
    extras_extraidos = {c.nome: "Não localizado" for c in campos_extras}

    campos = {
        "Data de Elaboração:": "data_elaboracao",
        "Número SEI:": "numero_sei",
        "Organograma:": "organograma",
        "Tipo de Documento:": "tipo_documento",
        "Abrangência:": "abrangencia",
        "Código do Documento:": "codigo_documento",
        "Título do Documento:": "titulo_documento",
    }
    rotulos_extras = {f"{c.rotulo}:": c.nome for c in campos_extras}

    for line in (ln.strip() for ln in response_text.split("\n") if ln.strip()):
        matched = False
        for prefixo, chave in campos.items():
            if prefixo in line:
                extracted[chave] = line.split(":", 1)[1].strip()
                matched = True
                break
        if matched:
            continue
        for prefixo, chave in rotulos_extras.items():
            if prefixo in line:
                extras_extraidos[chave] = line.split(":", 1)[1].strip()
                matched = True
                break
        if matched:
            continue
        if "Vencimento:" in line or "Revisão:" in line:
            extracted["vencimento"] = line.split(":", 1)[1].strip()
        elif "Elaboradores:" in line:
            elaboradores = line.split(":", 1)[1].strip()
            extracted["elaboradores"] = [e.strip() for e in elaboradores.split(",")]
    extracted["campos_extras"] = extras_extraidos
    return extracted


def init_routes(app):
    @app.route("/miac/obter-dados", methods=["POST"])
    def obter_dados():
        if "username" not in session:
            return jsonify({"error": "Usuário não autenticado"}), 403

        upload_folder = current_app.config["UPLOAD_FOLDER"]
        ia_config = IaConfig.get()
        deepseek_key = ia_config.deepseek_api_key or current_app.config["DEEPSEEK_API_KEY"]
        openai_key = ia_config.openai_api_key or current_app.config["OPENAI_API_KEY"]
        campos_extras_ativos = (
            CampoExtracao.query.filter_by(ativo=True)
            .order_by(CampoExtracao.ordem, CampoExtracao.id)
            .all()
        )

        try:
            files = request.files.getlist("pdf_file")
            modelo_ia = request.form.get("modelo_ia") or ia_config.modelo_padrao
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
                        logger.info(
                            "[IA] PDF %s texto extraído: %d chars\n--- INÍCIO ---\n%s\n--- FIM ---",
                            file.filename,
                            len(pdf_text) if pdf_text else 0,
                            pdf_text if pdf_text else "(vazio)",
                        )
                        if pdf_text is None or len(pdf_text.strip()) < 20:
                            raise RuntimeError(
                                f"Texto não encontrado ou insuficiente no PDF: {file.filename}"
                            )

                        prompt = _build_prompt(pdf_text, campos_extras_ativos)
                        logger.info("[IA] prompt enviado (%d chars):\n%s", len(prompt), prompt)
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

                        logger.info(
                            "[IA] resposta bruta para %s:\n%s",
                            file.filename, gpt_response,
                        )
                        extracted = _parse_gpt_response(
                            gpt_response, file.filename, campos_extras_ativos
                        )
                        logger.info("[IA] extração final: %s", extracted)

                        extracted["abrangencia"] = (
                            resolver_abrangencia(extracted["abrangencia"])
                            or "Não localizado"
                        )
                        extracted["organograma"] = (
                            resolver_organograma(extracted["organograma"])
                            or "Não localizado"
                        )
                        extracted["tipo_documento"] = (
                            resolver_tipo_documento(extracted["tipo_documento"])
                            or "Não localizado"
                        )

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
                                "campos_extras": extracted["campos_extras"],
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
                            except OSError:
                                logger.warning(
                                    "Falha ao remover arquivo temporário %s",
                                    file_path,
                                    exc_info=True,
                                )

            return jsonify(resultados)

        except Exception as exc:
            logger.exception("Erro ao processar arquivos enviados para IA")
            return jsonify({"error": f"Erro ao processar arquivos: {exc}"}), 500
