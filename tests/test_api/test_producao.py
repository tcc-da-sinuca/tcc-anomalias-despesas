"""Modo de produção (PRODUCAO=1): proxy HTTPS, cookies seguros e recusa de senhas de exemplo."""

import pytest

CHAVE_FORTE = "x" * 48


def _config(**extra):
    from app.config import TestConfig

    return type(
        "ConfigProducao", (TestConfig,), {"PRODUCAO": True, "SECRET_KEY": CHAVE_FORTE, **extra}
    )


@pytest.mark.parametrize("chave", ["troque-esta-chave", "chave-de-teste", "curta-demais", ""])
def test_recusa_chave_de_exemplo_ou_curta(chave):
    from app import ConfiguracaoInseguraError, create_app

    with pytest.raises(ConfiguracaoInseguraError, match="SECRET_KEY"):
        create_app(_config(SECRET_KEY=chave))


@pytest.fixture
def app_producao():
    from app import create_app
    from app.extensoes import db

    app = create_app(_config())
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def test_cookies_seguros_e_proxy(app_producao):
    from werkzeug.middleware.proxy_fix import ProxyFix

    assert isinstance(app_producao.wsgi_app, ProxyFix)
    assert app_producao.config["SESSION_COOKIE_SECURE"] is True
    assert app_producao.config["REMEMBER_COOKIE_SECURE"] is True


def test_redirecionamento_usa_https_informado_pelo_nginx(app_producao):
    resposta = app_producao.test_client().get(
        "/alertas",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "anomalias.exemplo.com"},
    )
    assert resposta.status_code == 302
    assert resposta.headers["Location"].startswith("/login")  # relativo: mantém o https do proxy


def test_cookie_de_sessao_marcado_como_seguro(app_producao):
    from app.extensoes import db
    from app.servicos.usuarios import criar_usuario

    criar_usuario("Auditora", "auditora@exemplo.com", "senha-segura-123", "auditor")
    db.session.commit()
    resposta = app_producao.test_client().post(
        "/login",
        data={"email": "auditora@exemplo.com", "senha": "senha-segura-123"},
        headers={"X-Forwarded-Proto": "https"},
        base_url="https://anomalias.exemplo.com",
    )
    cookie = next(c for c in resposta.headers.getlist("Set-Cookie") if c.startswith("session="))
    assert "Secure" in cookie and "HttpOnly" in cookie


@pytest.mark.parametrize("senha", ["troque-esta-senha", "curta"])
def test_seed_admin_recusa_senha_fraca(app_producao, monkeypatch, senha):
    monkeypatch.setenv("ADMIN_EMAIL", "admin@exemplo.com")
    monkeypatch.setenv("ADMIN_SENHA", senha)
    resultado = app_producao.test_cli_runner().invoke(args=["seed-admin"])
    assert resultado.exit_code != 0
    assert "pelo menos 12 caracteres" in resultado.output


def test_erro_interno_mostra_pagina_amigavel(app_producao):
    @app_producao.route("/falha-de-teste")
    def falhar():
        raise RuntimeError("falha simulada")

    app_producao.config["PROPAGATE_EXCEPTIONS"] = False
    resposta = app_producao.test_client().get("/falha-de-teste")

    assert resposta.status_code == 500
    html = resposta.get_data(as_text=True)
    assert "Erro interno" in html
    assert "falha simulada" not in html and "Traceback" not in html


def test_desenvolvimento_continua_sem_ajustes_de_producao(app):
    assert app.config.get("PRODUCAO") is False
    assert app.config.get("SESSION_COOKIE_SECURE") is False
