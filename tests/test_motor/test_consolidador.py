"""Consolidador: executa os detectores e gera os dados dos alertas."""

import pytest

from motor.consolidador import (
    COLUNAS_ALERTA,
    DETECTORES,
    MetodoDesconhecidoError,
    consolidar,
    executar_detectores,
)
from tests.test_motor.auxiliares import grupo_com_extremo, montar_despesas


@pytest.fixture
def despesas():
    linhas = grupo_com_extremo(n_normais=199)
    linhas.append({"valor": 100.0, "centro_custo": "CC-TI"})  # combinação inexistente
    return montar_despesas(linhas)


def test_executa_todos_os_metodos_por_padrao(despesas):
    resultados = executar_detectores(despesas, {})

    assert set(resultados) == set(DETECTORES)
    assert all(len(r) == len(despesas) for r in resultados.values())


def test_repassa_os_parametros_de_cada_metodo(despesas):
    resultados = executar_detectores(despesas, {"zscore": {"limiar": 1000.0}}, ["zscore"])
    assert not resultados["zscore"]["sinalizado"].any()


def test_metodo_desconhecido(despesas):
    with pytest.raises(MetodoDesconhecidoError, match="xyz"):
        executar_detectores(despesas, {}, ["zscore", "xyz"])


def test_um_alerta_por_despesa_e_metodo(despesas):
    alertas = consolidar(executar_detectores(despesas, {}, ["zscore", "iqr", "contextual"]))

    assert tuple(alertas.columns) == COLUNAS_ALERTA
    pares = set(zip(alertas["despesa_id"], alertas["metodo"], strict=True))
    assert pares == {(200, "zscore"), (200, "iqr"), (201, "contextual")}
    assert (alertas["motivo"] != "").all()


def test_nada_sinalizado():
    despesas = montar_despesas([{"valor": 100.0 + i % 3} for i in range(20)])
    alertas = consolidar(executar_detectores(despesas, {}, ["zscore", "iqr", "contextual"]))

    assert alertas.empty
    assert tuple(alertas.columns) == COLUNAS_ALERTA


def test_parametros_padrao_coincidem_com_os_da_aplicacao():
    from app.models.dominio import PARAMETROS_PADRAO
    from motor.consolidador import parametros_padrao

    for metodo, parametros in parametros_padrao().items():
        esperado = {chave: float(valor) for chave, valor in PARAMETROS_PADRAO[metodo].items()}
        assert parametros == esperado
