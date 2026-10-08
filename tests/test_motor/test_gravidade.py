"""Gravidade do alerta: quanto o score passou do limite do método."""

import pandas as pd
import pytest

from motor import gravidade
from motor.consolidador import consolidar, executar_detectores
from tests.test_motor.auxiliares import grupo_com_extremo, montar_despesas


@pytest.mark.parametrize(
    ("metodo", "excesso", "nivel"),
    [
        ("zscore", 1.0, "leve"),
        ("zscore", 1.49, "leve"),
        ("zscore", 1.5, "moderada"),
        ("zscore", 2.0, "alta"),
        ("zscore", 3.5, "critica"),
        ("zscore", 40.0, "critica"),
        ("iqr", 1.2, "leve"),
        ("iqr", 9.0, "critica"),
        ("isolation_forest", 1.1, "leve"),
        ("isolation_forest", 1.3, "critica"),
        ("contextual", 1.5, "leve"),
        ("contextual", 3.0, "moderada"),
        ("contextual", 100.0, "alta"),  # a regra contextual nunca chega a crítica
    ],
)
def test_classificar(metodo, excesso, nivel):
    assert gravidade.classificar(metodo, excesso) == nivel


def test_excesso_desconhecido():
    assert gravidade.classificar("zscore", None) is None
    assert gravidade.classificar("zscore", float("nan")) is None


def test_mais_grave():
    assert gravidade.mais_grave(["leve", "alta", None, "moderada"]) == "alta"
    assert gravidade.mais_grave([None]) is None


def test_excesso_e_o_score_sobre_o_limite():
    despesas = montar_despesas(grupo_com_extremo())
    resultados = executar_detectores(despesas, {"zscore": {"limiar": 2.0}}, ["zscore"])
    ultima = resultados["zscore"].iloc[-1]

    assert ultima["excesso"] == pytest.approx(ultima["score"] / 2.0)


def test_consolidar_inclui_a_gravidade():
    despesas = montar_despesas(grupo_com_extremo())
    alertas = consolidar(executar_detectores(despesas, {}, ["zscore"]))

    linha = alertas.iloc[0]
    assert linha["gravidade"] == gravidade.classificar("zscore", linha["excesso"])
    assert linha["gravidade"] in gravidade.NIVEIS


def test_contextual_inexistente_e_alta():
    linhas = [{"valor": 100.0}] * 499 + [{"valor": 100.0, "centro_custo": "CC-TI"}]
    alertas = consolidar(executar_detectores(montar_despesas(linhas), {}, ["contextual"]))

    assert alertas["gravidade"].tolist() == ["alta"]
    assert isinstance(alertas, pd.DataFrame)
