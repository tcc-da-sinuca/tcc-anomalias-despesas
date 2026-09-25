"""Tela de gerenciamento de usuários (somente administrador)."""

import pytest

from tests.conftest import SENHA_TESTE


def test_somente_administrador(client, entrar, auditor):
    entrar(auditor)
    assert client.get("/usuarios").status_code == 403
    assert client.post("/usuarios", data={"nome": "X"}).status_code == 403
    assert "Usuários" not in client.get("/").get_data(as_text=True)


def test_lista_usuarios(client, entrar, administrador, auditor, usuario_inativo):
    entrar(administrador)
    html = client.get("/usuarios").get_data(as_text=True)

    assert auditor.email in html and usuario_inativo.email in html
    assert "inativo</span>" in html
    assert ">Usuários</a>" in html  # item de menu do administrador


def test_criar_usuario(client, entrar, administrador, sessao):
    from app.servicos.usuarios import buscar_por_email

    entrar(administrador)
    resposta = client.post(
        "/usuarios",
        data={
            "nome": "Nova Auditora",
            "email": "Nova@Teste.com",
            "perfil": "auditor",
            "senha": "senha-forte-1",
        },
        follow_redirects=True,
    )

    assert "Usuário nova@teste.com criado como auditor." in resposta.get_data(as_text=True)
    novo = buscar_por_email("nova@teste.com")
    assert novo.verificar_senha("senha-forte-1")


@pytest.mark.parametrize(
    ("dados", "mensagem"),
    [
        ({"nome": "X", "email": "x@t.com", "perfil": "auditor", "senha": "curta"}, "pelo menos 8"),
        (
            {
                "nome": "X",
                "email": "auditor@teste.com",
                "perfil": "auditor",
                "senha": "senha-forte-1",
            },
            "Já existe",
        ),
        (
            {"nome": "X", "email": "x@t.com", "perfil": "gestor", "senha": "senha-forte-1"},
            "Perfil inválido",
        ),
    ],
)
def test_criar_usuario_invalido(client, entrar, administrador, auditor, dados, mensagem):
    entrar(administrador)
    resposta = client.post("/usuarios", data=dados)

    html = resposta.get_data(as_text=True)
    assert resposta.status_code == 400
    assert mensagem in html
    assert f'value="{dados["email"]}"' in html  # mantém o que foi digitado, menos a senha


def test_trocar_perfil_e_desativar(client, entrar, administrador, auditor, sessao):
    entrar(administrador)
    client.post(f"/usuarios/{auditor.id}/perfil", data={"perfil": "administrador"})
    sessao.refresh(auditor)
    assert auditor.perfil == "administrador"

    html = client.post(
        f"/usuarios/{auditor.id}/ativo", data={"ativo": "0"}, follow_redirects=True
    ).get_data(as_text=True)
    sessao.refresh(auditor)
    assert not auditor.ativo
    assert "desativado" in html


def test_protecao_contra_si_mesmo(client, entrar, administrador):
    entrar(administrador)
    html = client.post(
        f"/usuarios/{administrador.id}/ativo", data={"ativo": "0"}, follow_redirects=True
    ).get_data(as_text=True)
    assert "Você não pode desativar a si mesmo." in html


def test_usuario_desativado_perde_a_sessao_aberta(app, auditor, administrador, sessao):
    from app.servicos.usuarios import definir_ativo

    cliente_auditor = app.test_client()
    cliente_auditor.post("/login", data={"email": auditor.email, "senha": SENHA_TESTE})
    assert cliente_auditor.get("/alertas").status_code == 200

    definir_ativo(auditor, False, administrador)
    sessao.commit()

    resposta = cliente_auditor.get("/alertas")
    assert resposta.status_code == 302
    assert "/login" in resposta.headers["Location"]
    assert cliente_auditor.get("/api/alertas").status_code == 401


def test_usuario_inexistente(client, entrar, administrador):
    entrar(administrador)
    assert client.post("/usuarios/999/ativo", data={"ativo": "0"}).status_code == 404
