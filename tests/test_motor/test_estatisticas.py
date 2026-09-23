"""Estatísticas de referência por grupo (função pura do motor)."""

from decimal import Decimal

import pandas as pd
import pytest

from motor.estatisticas import COLUNAS_RESULTADO, calcular_estatisticas


@pytest.fixture
def despesas():
    return pd.DataFrame(
        {
            "valor": [Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40"), Decimal("100")],
            "categoria": ["Viagens", "Viagens", "Viagens", "Viagens", "Software"],
            "conta_contabil": ["3.1", "3.1", "3.2", "3.2", "3.2"],
            "centro_custo": ["CC-01"] * 5,
        }
    )


def _grupo(estatisticas, dimensao, chave):
    linha = estatisticas[(estatisticas["dimensao"] == dimensao) & (estatisticas["chave"] == chave)]
    assert len(linha) == 1
    return linha.iloc[0]


def test_valores_calculados_a_mao(despesas):
    estatisticas = calcular_estatisticas(despesas)
    viagens = _grupo(estatisticas, "categoria", "Viagens")

    assert viagens["n"] == 4
    assert viagens["media"] == pytest.approx(25.0)
    assert viagens["desvio"] == pytest.approx(12.909944, rel=1e-6)  # amostral (n - 1)
    assert viagens["q1"] == pytest.approx(17.5)  # interpolação linear
    assert viagens["q3"] == pytest.approx(32.5)


def test_uma_linha_por_grupo_de_cada_dimensao(despesas):
    estatisticas = calcular_estatisticas(despesas)

    assert tuple(estatisticas.columns) == COLUNAS_RESULTADO
    contagem = estatisticas.groupby("dimensao").size().to_dict()
    assert contagem == {"categoria": 2, "conta_contabil": 2, "centro_custo": 1}
    assert _grupo(estatisticas, "centro_custo", "CC-01")["n"] == 5
    assert _grupo(estatisticas, "conta_contabil", "3.2")["media"] == pytest.approx(170 / 3)


def test_grupo_com_uma_despesa_nao_tem_desvio(despesas):
    software = _grupo(calcular_estatisticas(despesas), "categoria", "Software")

    assert software["n"] == 1
    assert software["desvio"] is None
    assert software["q1"] == software["q3"] == pytest.approx(100.0)


def test_sem_despesas():
    vazio = pd.DataFrame(columns=["valor", "categoria", "conta_contabil", "centro_custo"])
    estatisticas = calcular_estatisticas(vazio)

    assert estatisticas.empty
    assert tuple(estatisticas.columns) == COLUNAS_RESULTADO


def test_dimensoes_escolhidas(despesas):
    estatisticas = calcular_estatisticas(despesas, dimensoes=("categoria",))
    assert set(estatisticas["dimensao"]) == {"categoria"}
