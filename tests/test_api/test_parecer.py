"""API de parecer: POST /api/alertas/{id}/parecer (US07, US08)."""

import pytest


def _enviar(client, alerta_id, **corpo):
    return client.post(f"/api/alertas/{alerta_id}/parecer", json=corpo)


def test_exige_login(client, alerta):
    assert _enviar(client, alerta.id, status="aprovado").status_code == 401


def test_registrar_parecer(client, entrar, auditor, alerta):
    entrar(auditor)
    resposta = _enviar(client, alerta.id, status="irregular", observacao="Valor sem nota fiscal.")

    assert resposta.status_code == 201
    dados = resposta.get_json()
    assert dados["status"] == dados["status_revisao"] == "irregular"
    assert dados["usuario_id"] == auditor.id
    assert dados["observacao"] == "Valor sem nota fiscal."

    detalhe = client.get(f"/api/alertas/{alerta.id}").get_json()
    assert detalhe["status_revisao"] == "irregular"
    assert [p["status"] for p in detalhe["pareceres"]] == ["irregular"]


@pytest.mark.parametrize(
    ("corpo", "campo"),
    [
        ({"status": "irregular"}, "observacao"),
        ({"status": "necessita_justificativa", "observacao": " "}, "observacao"),
        ({"status": "pendente"}, "status"),
        ({}, "status"),
        ({"status": "aprovado", "observacao": 123}, "observacao"),
    ],
)
def test_parecer_invalido(client, entrar, auditor, alerta, corpo, campo):
    entrar(auditor)
    resposta = _enviar(client, alerta.id, **corpo)

    assert resposta.status_code == 400
    assert resposta.get_json()["campo"] == campo
    assert client.get(f"/api/alertas/{alerta.id}").get_json()["pareceres"] == []


def test_alerta_inexistente(client, entrar, auditor):
    entrar(auditor)
    assert _enviar(client, 999, status="aprovado").status_code == 404
