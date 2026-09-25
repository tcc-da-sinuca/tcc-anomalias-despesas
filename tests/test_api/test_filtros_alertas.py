"""Filtros combináveis da lista de alertas (US10)."""

from datetime import date
from decimal import Decimal

import pytest


@pytest.fixture
def alertas(sessao, auditor):
    """Quatro alertas em despesas diferentes, cada uma variando um campo."""
    from app.models import AlertaAnomalia, Despesa, ExecucaoAnalise

    execucao = ExecucaoAnalise(parametros={}, seed=42, executada_por=auditor.id)
    dados = [
        # (data, categoria, conta, centro, funcionário, método, status)
        (date(2026, 3, 5), "Viagens", "3.1.01", "CC-ADM", "F001", "zscore", "pendente"),
        (date(2026, 3, 20), "Viagens", "3.1.01", "CC-TI", "F002", "iqr", "irregular"),
        (date(2026, 4, 10), "Software", "3.5.01", "CC-TI", "F002", "contextual", "pendente"),
        (date(2026, 5, 1), "Viagens", "3.1.02", "CC-ADM", "F001", "isolation_forest", "aprovado"),
    ]
    objetos = [execucao]
    for dia, categoria, conta, centro, funcionario, metodo, status in dados:
        despesa = Despesa(
            valor=Decimal("100.00"),
            data=dia,
            categoria=categoria,
            conta_contabil=conta,
            centro_custo=centro,
            funcionario=funcionario,
        )
        objetos += [
            despesa,
            AlertaAnomalia(
                despesa=despesa,
                execucao=execucao,
                metodo=metodo,
                score=1.0,
                motivo="m",
                status_revisao=status,
            ),
        ]
    sessao.add_all(objetos)
    sessao.commit()
    return execucao


def _metodos(client, consulta=""):
    resposta = client.get(f"/api/alertas?{consulta}")
    assert resposta.status_code == 200, resposta.get_json()
    return sorted(a["metodo"] for a in resposta.get_json()["itens"])


@pytest.mark.parametrize(
    ("consulta", "esperado"),
    [
        ("", ["contextual", "iqr", "isolation_forest", "zscore"]),
        ("data_inicio=2026-03-20", ["contextual", "iqr", "isolation_forest"]),
        ("data_fim=2026-03-20", ["iqr", "zscore"]),  # limites inclusivos
        ("data_inicio=2026-03-01&data_fim=2026-03-31", ["iqr", "zscore"]),
        ("categoria=Software", ["contextual"]),
        ("conta_contabil=3.1.02", ["isolation_forest"]),
        ("centro_custo=CC-TI", ["contextual", "iqr"]),
        ("funcionario=F001", ["isolation_forest", "zscore"]),
        ("status=pendente", ["contextual", "zscore"]),
        ("metodo=iqr", ["iqr"]),
    ],
)
def test_cada_filtro(client, entrar, auditor, alertas, consulta, esperado):
    entrar(auditor)
    assert _metodos(client, consulta) == esperado


def test_filtros_combinados(client, entrar, auditor, alertas):
    entrar(auditor)
    assert _metodos(client, "categoria=Viagens&centro_custo=CC-ADM") == [
        "isolation_forest",
        "zscore",
    ]
    assert _metodos(client, "categoria=Viagens&centro_custo=CC-ADM&status=pendente") == ["zscore"]
    assert _metodos(client, "funcionario=F002&data_inicio=2026-04-01&metodo=contextual") == [
        "contextual"
    ]
    assert _metodos(client, "categoria=Software&funcionario=F001") == []


def test_campos_vazios_nao_filtram(client, entrar, auditor, alertas):
    entrar(auditor)
    campos = "data_inicio data_fim categoria conta_contabil centro_custo funcionario status metodo"
    consulta = "&".join(f"{campo}=" for campo in campos.split())
    assert len(_metodos(client, consulta)) == 4


@pytest.mark.parametrize(
    ("consulta", "campo"),
    [
        ("data_inicio=05/03/2026", "data_inicio"),
        ("data_fim=2026-13-01", "data_fim"),
        ("data_inicio=2026-04-01&data_fim=2026-03-01", "data_fim"),
        ("status=qualquer", "status"),
        ("metodo=qualquer", "metodo"),
        ("execucao_id=abc", "execucao_id"),
    ],
)
def test_filtro_invalido(client, entrar, auditor, consulta, campo):
    entrar(auditor)
    resposta = client.get(f"/api/alertas?{consulta}")

    assert resposta.status_code == 400
    assert resposta.get_json()["campo"] == campo
