"""Smoke tests de rotas principais: auth guard e login flow."""


def test_login_get_retorna_200(client):
    resp = client.get("/miac/login")
    assert resp.status_code == 200


def test_index_sem_login_redireciona(client):
    resp = client.get("/miac/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_admin_panel_exige_nivel_elevado(client):
    resp = client.get("/miac/admin", follow_redirects=False)
    assert resp.status_code == 302


def test_login_sucesso_redireciona_para_index(client):
    resp = client.post(
        "/miac/login",
        data={"username": "teste", "password": "senha123"},
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_login_credencial_invalida_retorna_200_com_erro(client):
    resp = client.post(
        "/miac/login",
        data={"username": "teste", "password": "errada"},
    )
    assert resp.status_code == 200
    assert b"inv" in resp.data.lower()


def test_logged_client_acessa_admin(logged_client):
    resp = logged_client.get("/miac/admin")
    assert resp.status_code == 200
    assert b"Organogramas" in resp.data


def test_logged_client_cria_abrangencia(logged_client):
    resp = logged_client.post(
        "/miac/admin/abrangencia",
        data={"acao": "add", "nome": "novo"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    follow = logged_client.get("/miac/admin")
    assert b"NOVO" in follow.data


def test_publicados_renderiza_com_filtros_padrao(logged_client):
    resp = logged_client.get("/miac/publicados")
    assert resp.status_code == 200
    # Filtros padrão foram semeados
    assert b"Organograma" in resp.data
    assert b"Tipo de documento" in resp.data


def test_admin_filtro_publicados_toggle(logged_client, app):
    from app.models import FiltroPublicados

    with app.app_context():
        filtro = FiltroPublicados.query.filter_by(campo_ref="organograma").first()
        assert filtro is not None
        fid = filtro.id
        ativo_antes = filtro.ativo

    resp = logged_client.post(
        "/miac/admin/filtro_publicados",
        data={"acao": "toggle", "id": fid},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    with app.app_context():
        filtro = FiltroPublicados.query.get(fid)
        assert filtro.ativo != ativo_antes


def test_identidade_persiste_cores_e_nome(logged_client, app):
    from app.models import OrganizacaoConfig

    resp = logged_client.post(
        "/miac/admin/identidade",
        data={
            "nome_empresa": "Hospital Teste",
            "sigla_app": "HT",
            "cor_primaria": "#ff0000",
            "cor_sidebar": "#00ff00",
            "rodape": "Rodapé custom",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with app.app_context():
        org = OrganizacaoConfig.get()
        assert org.nome_empresa == "Hospital Teste"
        assert org.cor_primaria == "#ff0000"
        assert org.rodape == "Rodapé custom"
