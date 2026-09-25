"""API de análises e alertas (US03, US05, US06)."""

from datetime import date
from decimal import Decimal

import pytest


@pytest.fixture
def despesas(sessao):
    """120 despesas de Viagens em torno de R$ 100 e uma de R$ 2.500 (valor extremo)."""
    from app.models import Despesa

    valores = [f"{95 + i % 11}.00" for i in range(120)] + ["2500.00"]
    sessao.add_all(
        Despesa(
            valor=Decimal(v),
            data=date(2026, 3, 2),
            categoria="Viagens",
            conta_contabil="3.1.01",
            centro_custo="CC-ADM",
            funcionario="F001",
        )
        for v in valores
    )
    sessao.commit()


@pytest.mark.parametrize(
    ("metodo", "caminho"),
    [
        ("post", "/api/analises"),
        ("get", "/api/analises/1"),
        ("get", "/api/alertas"),
        ("get", "/api/alertas/1"),
    ],
)
def test_exigem_login(client, metodo, caminho):
    assert getattr(client, metodo)(caminho).status_code == 401


def test_executar_analise(client, entrar, auditor, despesas):
    entrar(auditor)
    resposta = client.post("/api/analises")

    assert resposta.status_code == 201
    execucao = resposta.get_json()
    # a despesa de R$ 2.500 é sinalizada pelo Z-score, pelo IQR e pelo Isolation Forest
    assert (execucao["total_despesas"], execucao["total_alertas"]) == (121, 3)
    assert execucao["alertas_por_metodo"] == {"iqr": 1, "isolation_forest": 1, "zscore": 1}
    assert execucao["seed"] == 42
    assert execucao["executada_por"] == auditor.id
    assert execucao["parametros"]["metodos"] == ["zscore", "iqr", "contextual", "isolation_forest"]

    consulta = client.get(f"/api/analises/{execucao['id']}")
    assert consulta.status_code == 200
    assert consulta.get_json()["total_alertas"] == 3


def test_executar_so_alguns_metodos(client, entrar, auditor, despesas):
    entrar(auditor)
    resposta = client.post("/api/analises", json={"metodos": ["zscore"]})

    assert resposta.status_code == 201
    assert resposta.get_json()["alertas_por_metodo"] == {"zscore": 1}


@pytest.mark.parametrize("corpo", [{"metodos": ["nao_existe"]}, {"metodos": "zscore"}])
def test_executar_com_metodo_invalido(client, entrar, auditor, despesas, corpo):
    entrar(auditor)
    resposta = client.post("/api/analises", json=corpo)

    assert resposta.status_code == 400
    assert "erro" in resposta.get_json()


def test_analise_inexistente(client, entrar, auditor):
    entrar(auditor)
    assert client.get("/api/analises/999").status_code == 404


def test_listar_alertas(client, entrar, auditor, despesas):
    entrar(auditor)
    client.post("/api/analises")

    dados = client.get("/api/alertas").get_json()

    assert dados["total"] == 3
    alerta = dados["itens"][0]
    assert alerta["status_revisao"] == "pendente"
    assert alerta["motivo"].startswith("Valor R$ 2.500,00")
    assert alerta["despesa"]["valor"] == "2500.00"
    scores = [a["score"] for a in dados["itens"]]
    assert scores == sorted(scores, reverse=True)  # maior score primeiro


def test_filtrar_alertas(client, entrar, auditor, despesas):
    entrar(auditor)
    client.post("/api/analises")

    assert client.get("/api/alertas?metodo=zscore").get_json()["total"] == 1
    assert client.get("/api/alertas?status=aprovado").get_json()["total"] == 0
    assert client.get("/api/alertas?execucao_id=999").get_json()["total"] == 0


@pytest.mark.parametrize("filtro", ["status=qualquer", "metodo=qualquer"])
def test_filtro_invalido(client, entrar, auditor, filtro):
    entrar(auditor)
    assert client.get(f"/api/alertas?{filtro}").status_code == 400


def test_detalhe_do_alerta(client, entrar, auditor, alerta):
    entrar(auditor)
    dados = client.get(f"/api/alertas/{alerta.id}").get_json()

    assert dados["metodo"] == "zscore"
    assert dados["despesa"]["categoria"] == "Viagens"
    assert dados["pareceres"] == []
    assert client.get("/api/alertas/999").status_code == 404
