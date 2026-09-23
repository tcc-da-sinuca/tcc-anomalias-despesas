"""Autenticação, controle por perfil e rotas básicas (RNF03, RNF04)."""

import pytest


def test_saude_responde_sem_login(client):
    resposta = client.get("/api/saude")
    assert resposta.status_code == 200
    assert resposta.get_json() == {"status": "ok", "banco": "ok"}


def test_pagina_inicial_exige_login(client):
    resposta = client.get("/")
    assert resposta.status_code == 302
    assert "/login" in resposta.headers["Location"]


def test_api_sem_login_responde_401_em_json(client):
    resposta = client.get("/api/usuario-atual")
    assert resposta.status_code == 401
    assert "erro" in resposta.get_json()


def test_login_com_credenciais_validas(client, entrar, auditor):
    resposta = entrar(auditor)
    assert resposta.status_code == 302
    dados = client.get("/api/usuario-atual").get_json()
    assert dados["email"] == "auditor@teste.com"
    assert dados["perfil"] == "auditor"


def test_login_com_senha_errada(client, entrar, auditor):
    resposta = entrar(auditor, senha="senha-errada")
    assert resposta.status_code == 401
    assert client.get("/api/usuario-atual").status_code == 401


def test_login_aceita_email_com_maiusculas(client, auditor):
    resposta = client.post(
        "/login", data={"email": "AUDITOR@Teste.com", "senha": "senha-segura-123"}
    )
    assert resposta.status_code == 302


def test_usuario_inativo_nao_entra(client, entrar, usuario_inativo):
    assert entrar(usuario_inativo).status_code == 401


def test_login_nao_redireciona_para_outro_site(client, auditor):
    resposta = client.post(
        "/login?next=//site-malicioso.com",
        data={"email": auditor.email, "senha": "senha-segura-123"},
    )
    assert resposta.status_code == 302
    assert "site-malicioso" not in resposta.headers["Location"]


def test_logout_encerra_a_sessao(client, entrar, auditor):
    entrar(auditor)
    client.post("/logout")
    assert client.get("/api/usuario-atual").status_code == 401


def test_pagina_inicial_mostra_aviso_de_indicio(client, entrar, auditor):
    entrar(auditor)
    html = client.get("/").get_data(as_text=True)
    assert "indícios estatísticos, não acusações" in html


# --- Controle por perfil ----------------------------------------------------


@pytest.fixture
def app_com_rota_admin(app):
    from app.models.dominio import PERFIL_ADMINISTRADOR
    from app.rotas.autorizacao import perfil_requerido

    @app.route("/somente-admin")
    @perfil_requerido(PERFIL_ADMINISTRADOR)
    def somente_admin():
        return "ok"

    return app


def test_rota_de_admin_bloqueia_auditor(app_com_rota_admin, client, entrar, auditor):
    entrar(auditor)
    assert client.get("/somente-admin").status_code == 403


def test_rota_de_admin_libera_administrador(app_com_rota_admin, client, entrar, administrador):
    entrar(administrador)
    assert client.get("/somente-admin").status_code == 200


def test_rota_de_admin_sem_login_vai_para_login(app_com_rota_admin, client):
    resposta = client.get("/somente-admin")
    assert resposta.status_code == 302
    assert "/login" in resposta.headers["Location"]


# --- Comando seed-admin -----------------------------------------------------


def test_seed_admin_e_idempotente(app, monkeypatch):
    from sqlalchemy import func, select

    from app.extensoes import db
    from app.models import ParametroMetodo, Usuario

    monkeypatch.setenv("ADMIN_EMAIL", "admin@exemplo.com")
    monkeypatch.setenv("ADMIN_SENHA", "senha-admin-123")
    runner = app.test_cli_runner()

    primeira = runner.invoke(args=["seed-admin"])
    segunda = runner.invoke(args=["seed-admin"])

    assert primeira.exit_code == 0, primeira.output
    assert "criado" in primeira.output
    assert segunda.exit_code == 0, segunda.output
    assert "já existe" in segunda.output
    assert db.session.scalar(select(func.count(Usuario.id))) == 1
    assert db.session.scalar(select(func.count()).select_from(ParametroMetodo)) == 5
    admin = db.session.scalar(select(Usuario))
    assert admin.perfil == "administrador"
    assert admin.verificar_senha("senha-admin-123")
