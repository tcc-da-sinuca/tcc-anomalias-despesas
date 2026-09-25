"""API do relatório mensal: GET /api/relatorios/mensal (US11)."""

import pytest


def test_exige_login(client):
    assert client.get("/api/relatorios/mensal?ano=2026&mes=9").status_code == 401


def test_json(client, entrar, auditor, alerta):
    entrar(auditor)
    dados = client.get("/api/relatorios/mensal?ano=2026&mes=9").get_json()

    assert (dados["ano"], dados["mes"], dados["inicio"], dados["fim"]) == (
        2026,
        9,
        "2026-09-01",
        "2026-09-30",
    )
    assert dados["valor_despesas"] == "1520.75"
    assert dados["total_alertas"] == 1
    assert dados["taxa_confirmacao"] is None
    assert dados["ultima_analise"]["id"] == alerta.execucao_id


def test_csv(client, entrar, auditor, alerta):
    entrar(auditor)
    resposta = client.get("/api/relatorios/mensal?ano=2026&mes=9&formato=csv")

    assert resposta.status_code == 200
    assert resposta.mimetype == "text/csv"
    assert 'filename="relatorio_2026_09.csv"' in resposta.headers["Content-Disposition"]
    texto = resposta.get_data(as_text=True)
    assert texto.startswith("﻿secao;item;valor")  # BOM para o Excel reconhecer UTF-8
    assert "resumo;valor_despesas;1520,75" in texto
    assert "resumo;taxa_confirmacao_percentual;\n" in texto  # indefinida = vazio


@pytest.mark.parametrize(
    "consulta", ["ano=2026", "mes=9", "ano=2026&mes=13", "ano=2026&mes=9&formato=pdf"]
)
def test_parametros_invalidos(client, entrar, auditor, consulta):
    entrar(auditor)
    assert client.get(f"/api/relatorios/mensal?{consulta}").status_code == 400
