/* publicar2.js — lógica da tela de publicação com fila de processamento por IA.
   URLs injetadas via window.MIAC_URLS no template. */

let arquivosProcessados = [];
let arquivoAtualIndex = 0;
let arquivosTotal = 0;
let arquivosProcessadosCount = 0;
let arquivosFalhas = [];
let limiteRequisicoesSimultaneas = 5;
let filaArquivos = [];
let arquivosEmProcesso = 0;
let tentativasReprocessamento = {};

$(document).ready(function () {
    // Alternar entre os formulários Manual e IA
    $('#manual-btn').click(function () {
        $('#form-manual').show();
        $('#form-ia').hide();
        $('#dados-extraidos').hide();
        $('#manual-btn').addClass('active');
        $('#ia-btn').removeClass('active');
    });
    $('#ia-btn').click(function () {
        $('#form-manual').hide();
        $('#form-ia').show();
        $('#dados-extraidos').hide();
        $('#ia-btn').addClass('active');
        $('#manual-btn').removeClass('active');
    });

    // Envio do formulário de IA
    $('#form-ia').submit(function (e) {
        e.preventDefault();
        $('#obter-loading').show();
        arquivosProcessados = [];
        arquivosFalhas = [];
        arquivosProcessadosCount = 0;
        const files = $('#pdf_file_ia')[0].files;
        arquivosTotal = files.length;
        const modeloIA = $('#modelo-ia').val();

        for (let i = 0; i < files.length; i++) {
            tentativasReprocessamento[i] = 0;
        }

        for (let i = 0; i < files.length; i++) {
            filaArquivos.push({ file: files[i], index: i });
        }

        processarFila(modeloIA);
    });

    function processarFila(modeloIA) {
        while (arquivosEmProcesso < limiteRequisicoesSimultaneas && filaArquivos.length > 0) {
            let item = filaArquivos.shift();
            arquivosEmProcesso++;
            processarArquivo(item.file, item.index, modeloIA);
        }
    }

    function processarArquivo(file, index, modeloIA) {
        console.log("Iniciando processamento do arquivo:", file.name, "com modelo IA:", modeloIA);
        let formData = new FormData();
        formData.append('pdf_file', file);
        formData.append('modelo_ia', modeloIA);

        $.ajax({
            url: window.MIAC_URLS.obter_dados,
            type: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            success: function (data) {
                console.log("Dados recebidos para o arquivo:", file.name, data);
                arquivosProcessados[index] = data[0];
                arquivosProcessadosCount++;
                $('#progresso').text(`Processados: ${arquivosProcessadosCount}/${arquivosTotal}`);
                if (arquivosProcessadosCount === arquivosTotal) {
                    finalizarProcessamento();
                }
                arquivosEmProcesso--;
                processarFila(modeloIA);
                mostrarDadosExtraidos(arquivoAtualIndex);
            },
            error: function (xhr, status, error) {
                console.error("Erro ao processar o arquivo:", file.name, error);
                arquivosFalhas.push(file.name);
                arquivosProcessadosCount++;
                arquivosEmProcesso--;
                processarFila(modeloIA);
            }
        });
    }

    function finalizarProcessamento() {
        $('#obter-loading').hide();
        $('#dados-extraidos').show();
        $('#nav-arquivos').show();
        $('#total-arquivos').text(arquivosProcessados.length);
        mostrarDadosExtraidos(0);
        $('#publicar-todos-btn').show();

        let arquivosComErro = [];
        arquivosProcessados.forEach((dados, index) => {
            let camposComErro = verificarCamposComErro(dados);
            if (camposComErro.length > 0) {
                arquivosComErro.push({
                    index: index,
                    nome: dados.gpt_response.titulo,
                    camposComErro: camposComErro.join(", ")
                });
            }
        });

        if (arquivosComErro.length > 0) {
            $('#arquivos-com-erro').show();
            $('#tabela-arquivos-erro').empty();
            arquivosComErro.forEach(arquivo => {
                $('#tabela-arquivos-erro').append(`
                    <tr data-index="${arquivo.index}">
                        <td>${arquivo.nome}</td>
                        <td>${arquivo.camposComErro}</td>
                        <td>
                            <input type="checkbox" class="arquivo-erro-checkbox" data-index="${arquivo.index}">
                            Selecionar
                        </td>
                    </tr>
                `);
            });
            $('#processar-novamente-btn').show();
            $('#continuar-editar-btn').show();
        }

        if (arquivosFalhas.length > 0) {
            alert(`Alguns arquivos falharam: ${arquivosFalhas.join(', ')}`);
        }
    }

    $('#processar-novamente-btn').click(function () {
        let arquivosSelecionados = [];
        const modeloIA = $('#modelo-ia').val();

        if (!modeloIA) {
            alert("Selecione um modelo de IA antes de reprocessar.");
            return;
        }

        $('.arquivo-erro-checkbox:checked').each(function () {
            let index = $(this).data('index');
            if (tentativasReprocessamento[index] < 2) {
                arquivosSelecionados.push(index);
            } else {
                alert(`O arquivo "${arquivosProcessados[index].gpt_response.titulo}" já atingiu o limite de reprocessamento.`);
            }
        });

        if (arquivosSelecionados.length === 0) {
            console.log("Nenhum arquivo disponível para reprocessamento.");
            return;
        }

        $('#processar-novamente-loading').show();
        try {
            arquivosSelecionados.forEach(index => {
                let file = $('#pdf_file_ia')[0].files[index];
                tentativasReprocessamento[index]++;
                console.log(`Reprocessando arquivo: ${file.name} com modelo IA: ${modeloIA}`);
                processarArquivo(file, index, modeloIA);
            });
        } catch (error) {
            console.error("Erro durante o reprocessamento:", error);
            alert("Ocorreu um erro durante o reprocessamento. Por favor, tente novamente.");
        }

        setTimeout(() => {
            atualizarInterfaceAposReprocessamento();
            $('#processar-novamente-loading').hide();
        }, 2000);
    });

    $('#continuar-editar-btn').click(function () {
        alert("Você escolheu continuar com os dados atuais. Edite manualmente os campos necessários.");
        $('#arquivos-com-erro').hide();
        $('#processar-novamente-btn').hide();
        $('#continuar-editar-btn').hide();
    });

    function atualizarInterfaceAposReprocessamento() {
        console.log("Atualizando interface após reprocessamento...");

        $('#tabela-arquivos-erro').empty();
        let arquivosComErro = [];
        arquivosProcessados.forEach((dados, index) => {
            let camposComErro = verificarCamposComErro(dados);
            if (camposComErro.length > 0) {
                arquivosComErro.push({
                    index: index,
                    nome: dados.gpt_response.titulo,
                    camposComErro: camposComErro.join(", ")
                });
            }
        });

        if (arquivosComErro.length > 0) {
            console.log("Ainda existem arquivos com erro. Atualizando lista...");
            alert("Atenção: Alguns arquivos ainda possuem erro no processamento. Tente novamente ou edite manualmente.");

            $('#arquivos-com-erro').show();
            arquivosComErro.forEach(arquivo => {
                $('#tabela-arquivos-erro').append(`
                    <tr data-index="${arquivo.index}">
                        <td>${arquivo.nome}</td>
                        <td>${arquivo.camposComErro}</td>
                        <td>
                            <input type="checkbox" class="arquivo-erro-checkbox" data-index="${arquivo.index}">
                            Selecionar
                        </td>
                    </tr>
                `);
            });
            $('#processar-novamente-btn').show();
            $('#continuar-editar-btn').show();
        } else {
            console.log("Nenhum erro encontrado. Ocultando a seção de erros.");
            $('#arquivos-com-erro').fadeOut(300, function () {
                $(this).hide();
                $('#tabela-arquivos-erro').empty();
            });
            $('#processar-novamente-btn').hide();
            $('#continuar-editar-btn').hide();
        }

        mostrarDadosExtraidos(arquivoAtualIndex);
    }

    function verificarCamposComErro(dados) {
        let camposComErro = [];
        if (dados.gpt_response.data_elaboracao === "Não localizado") camposComErro.push("Data de Elaboração");
        if (dados.gpt_response.vencimento === "Não localizado") camposComErro.push("Vencimento");
        if (dados.gpt_response.organograma === "Não localizado") camposComErro.push("Organograma");
        if (dados.gpt_response.tipo_documento === "Não localizado") camposComErro.push("Tipo de Documento");
        if (dados.gpt_response.abrangencia === "Não localizado") camposComErro.push("Abrangência");
        return camposComErro;
    }

    function mostrarDadosExtraidos(index) {
        if (arquivosProcessados.length === 0) return;
        let dados = arquivosProcessados[index].gpt_response;

        $('#titulo_ia').val(dados.titulo);
        $('#data_elaboracao').val(dados.data_elaboracao);
        $('#vencimento').val(dados.vencimento);
        $('#numero_sei').val(dados.numero_sei);
        $('#organograma_ia').val(dados.organograma);
        $('#tipo_documento_ia').val(dados.tipo_documento);
        $('#abrangencia_ia').val(dados.abrangencia);
        $('#elaboradores_ia').val(arquivosProcessados[index].elaboradores.join(', '));
        $('#arquivo-atual').text(`${index + 1} - ${dados.titulo}`);
    }

    function atualizarDadosComAlteracoesManuais(index) {
        let dados = arquivosProcessados[index].gpt_response;
        dados.titulo = $('#titulo_ia').val();
        dados.data_elaboracao = $('#data_elaboracao').val();
        dados.vencimento = $('#vencimento').val();
        dados.numero_sei = $('#numero_sei').val();
        dados.organograma = $('#organograma_ia').val();
        dados.tipo_documento = $('#tipo_documento_ia').val();
        dados.abrangencia = $('#abrangencia_ia').val();
        arquivosProcessados[index].elaboradores = $('#elaboradores_ia').val().split(',').map(el => el.trim());
    }

    $('#prev-arquivo').click(function () {
        if (arquivoAtualIndex > 0) {
            atualizarDadosComAlteracoesManuais(arquivoAtualIndex);
            arquivoAtualIndex--;
            mostrarDadosExtraidos(arquivoAtualIndex);
        }
    });

    $('#next-arquivo').click(function () {
        if (arquivoAtualIndex < arquivosProcessados.length - 1) {
            atualizarDadosComAlteracoesManuais(arquivoAtualIndex);
            arquivoAtualIndex++;
            mostrarDadosExtraidos(arquivoAtualIndex);
        }
    });

    $('#publicar-todos-btn').click(function () {
        atualizarDadosComAlteracoesManuais(arquivoAtualIndex);

        $('#publicar-todos-loading').show();
        let formData = new FormData();

        const files = $('#pdf_file_ia')[0].files;
        for (let i = 0; i < files.length; i++) {
            formData.append('pdf_file', files[i]);
        }

        arquivosProcessados.forEach((dados, index) => {
            formData.append('titulo[]', dados.gpt_response.titulo);
            formData.append('organograma[]', dados.gpt_response.organograma);
            formData.append('tipo_documento[]', dados.gpt_response.tipo_documento);
            formData.append('abrangencia[]', dados.gpt_response.abrangencia);
            formData.append('elaboradores[]', dados.elaboradores.join(', '));
            formData.append('numero_sei[]', dados.gpt_response.numero_sei);
            formData.append('vencimento[]', dados.gpt_response.vencimento);
            formData.append('data_elaboracao[]', dados.gpt_response.data_elaboracao);
        });

        $.ajax({
            url: window.MIAC_URLS.publicar2,
            type: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            success: function () {
                alert("Todos os documentos foram publicados com sucesso!");
                $('#publicar-todos-loading').hide();

                $('#titulo_ia').val('');
                $('#data_elaboracao').val('');
                $('#vencimento').val('');
                $('#numero_sei').val('');
                $('#organograma_ia').val('');
                $('#tipo_documento_ia').val('');
                $('#abrangencia_ia').val('');
                $('#elaboradores_ia').val('');

                $('#arquivos-com-erro').hide();
                $('#processar-novamente-btn').hide();
                $('#continuar-editar-btn').hide();
                $('#tabela-arquivos-erro').empty();

                mostrarDadosExtraidos(0);
            },
            error: function (xhr, status, error) {
                alert("Erro ao publicar os documentos: " + error);
                $('#publicar-todos-loading').hide();
            }
        });
    });
});

function publicarManual(event) {
    event.preventDefault();
    const files = $('#pdf_file_manual')[0].files;

    if (files.length === 0) {
        alert("Selecione pelo menos um arquivo PDF");
        return;
    }

    const dataElaboracao = new Date($('#data_elaboracao_manual').val());
    const dataVencimento = new Date($('#vencimento_manual').val());

    if (dataVencimento <= dataElaboracao) {
        alert("A data de vencimento deve ser posterior à data de elaboração");
        return;
    }

    const formData = new FormData();

    for (let i = 0; i < files.length; i++) {
        formData.append('pdf_file', files[i]);
    }

    formData.append('titulo[]', $('#titulo_manual').val());
    formData.append('organograma[]', $('#organograma_manual').val());
    formData.append('tipo_documento[]', $('#tipo_documento_manual').val());
    formData.append('abrangencia[]', $('#abrangencia_manual').val());
    formData.append('data_elaboracao[]', $('#data_elaboracao_manual').val());
    formData.append('vencimento[]', $('#vencimento_manual').val());
    formData.append('numero_sei[]', $('#numero_sei_manual').val());
    formData.append('elaboradores[]', $('#elaboradores_manual').val());

    $('#publicar-loading').show();

    $.ajax({
        url: window.MIAC_URLS.publicar2,
        type: 'POST',
        data: formData,
        processData: false,
        contentType: false,
        success: function (response) {
            alert(`${files.length} documento(s) publicado(s) com sucesso!`);
            $('#form-manual')[0].reset();
        },
        error: function (xhr) {
            alert(`Erro: ${xhr.responseText || 'Falha na publicação'}`);
        },
        complete: function () {
            $('#publicar-loading').hide();
        }
    });
}
