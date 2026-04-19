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
