"""Detector Isolation Forest com atributos derivados (US04)."""

import pandas as pd
import pytest

from motor import isolation_forest as iforest
from motor.contrato import COLUNAS_RESULTADO
from tests.test_motor.auxiliares import montar_despesas

# 02/03/2026 é uma segunda-feira; 21/04/2026 é Tiradentes; 07/03/2026 é sábado.
SEGUNDA = pd.Timestamp("2026-03-02")


def _normais(quantidade=200):
    """Despesas comuns: dias úteis, valores variados, funcionários diferentes, longe do limite."""
    linhas = []
    for i in range(quantidade):
        linhas.append(
            {
                "valor": 100.0 + (i * 37) % 300,
                "data": SEGUNDA + pd.offsets.BDay(i % 60),
                "funcionario": f"F{i % 40:03d}",
                "categoria": "Viagens" if i % 2 else "Software",
            }
        )
    return linhas


def _atributos_da_ultima(linhas, **kwargs):
    despesas = montar_despesas(linhas)
    return iforest.atributos(despesas, **kwargs).iloc[-1]


def test_fim_semana_e_feriado():
    assert (
        _atributos_da_ultima([{"valor": 100.0, "data": pd.Timestamp("2026-03-07")}])[
            "fim_semana_feriado"
        ]
        == 1
    )
    assert (
        _atributos_da_ultima([{"valor": 100.0, "data": pd.Timestamp("2026-04-21")}])[
            "fim_semana_feriado"
        ]
        == 1
    )
    assert _atributos_da_ultima([{"valor": 100.0, "data": SEGUNDA}])["fim_semana_feriado"] == 0


def test_repeticoes_do_mesmo_valor_na_janela():
    base = {"valor": 350.0, "funcionario": "F012", "categoria": "Software"}
    linhas = [
        {**base, "data": SEGUNDA},
        {**base, "data": SEGUNDA + pd.DateOffset(days=7)},  # no limite da janela
        {**base, "data": SEGUNDA + pd.DateOffset(days=30)},  # fora da janela
        {**base, "funcionario": "F013", "data": SEGUNDA},  # outro funcionário
        {**base, "valor": 351.0, "data": SEGUNDA},  # outro valor
    ]
    tabela = iforest.atributos(montar_despesas(linhas))

    assert tabela["repeticoes_valor"].tolist() == [1, 1, 0, 0, 0]


def test_fracionamento_logo_abaixo_do_limite():
    base = {"funcionario": "F007", "categoria": "Software"}
    linhas = [
        {**base, "valor": 950.0, "data": SEGUNDA},
        {**base, "valor": 900.0, "data": SEGUNDA + pd.DateOffset(days=2)},
        {**base, "valor": 880.0, "data": SEGUNDA + pd.DateOffset(days=5)},
        {**base, "valor": 1000.0, "data": SEGUNDA},  # no limite: fora da faixa
        {**base, "valor": 800.0, "data": SEGUNDA},  # abaixo de 85%
        {**base, "valor": 960.0, "data": SEGUNDA + pd.DateOffset(days=20)},  # longe no tempo
    ]
    tabela = iforest.atributos(montar_despesas(linhas))

    assert tabela["fracionamento"].tolist() == [2, 2, 2, 0, 0, 0]


def test_limite_de_aprovacao_configuravel():
    linhas = [{"valor": 450.0, "data": SEGUNDA}, {"valor": 470.0, "data": SEGUNDA}]
    assert _atributos_da_ultima(linhas)["fracionamento"] == 0
    assert _atributos_da_ultima(linhas, limite_aprovacao=500.0)["fracionamento"] == 1


def test_desvio_do_valor_em_log_por_categoria():
    linhas = [{"valor": 100.0 + i} for i in range(30)] + [{"valor": 5000.0}]
    atributo = _atributos_da_ultima(linhas)

    assert atributo["desvio_valor"] > 5
    assert atributo["z_log_valor"] > 0


@pytest.fixture
def despesas_com_anomalias():
    linhas = _normais()
    linhas.append({"valor": 150.0, "data": pd.Timestamp("2026-03-08")})  # domingo
    duplicada = {"valor": 432.10, "funcionario": "F099", "categoria": "Viagens"}
    linhas += [
        {**duplicada, "data": SEGUNDA},
        {**duplicada, "data": SEGUNDA + pd.DateOffset(days=1)},
    ]
    fracionada = {"funcionario": "F098", "categoria": "Software"}
    linhas += [
        {**fracionada, "valor": v, "data": SEGUNDA + pd.DateOffset(days=d)}
        for v, d in [(955.0, 0), (962.0, 1), (971.0, 2)]
    ]
    return montar_despesas(linhas)


def test_sinaliza_as_anomalias_com_motivo(despesas_com_anomalias):
    resultado = iforest.detectar(despesas_com_anomalias, contamination=0.04)
    sinalizadas = resultado[resultado["sinalizado"]]

    assert tuple(resultado.columns) == COLUNAS_RESULTADO
    assert len(resultado) == len(despesas_com_anomalias)
    assert set(range(201, 207)) <= set(sinalizadas["despesa_id"])
    motivos = sinalizadas.set_index("despesa_id")["motivo"]
    assert motivos[201] == "Lançada num domingo (08/03/2026)."
    assert "mesmo valor (R$ 432,10) na categoria Viagens mais 1 vez em até 7 dias" in motivos[202]
    assert "com mais 2 lançamentos do funcionário F098 na mesma faixa" in motivos[204]
    assert "(possível fracionamento)" in motivos[204]


def test_score_maior_para_as_anomalias(despesas_com_anomalias):
    score = iforest.detectar(despesas_com_anomalias).set_index("despesa_id")["score"]
    assert score.loc[201:206].min() > score.loc[1:200].median()


def test_mesma_seed_mesmo_resultado(despesas_com_anomalias):
    a = iforest.detectar(despesas_com_anomalias, random_state=7)
    b = iforest.detectar(despesas_com_anomalias, random_state=7)
    pd.testing.assert_frame_equal(a, b)


def test_motivo_sem_fator_isolado():
    despesa = pd.Series(
        {"valor": 100.0, "data": SEGUNDA, "categoria": "Viagens", "funcionario": "F1"}
    )
    atributo = pd.Series(
        {
            "desvio_valor": 1.0,
            "z_log_valor": 1.0,
            "fim_semana_feriado": 0,
            "repeticoes_valor": 0,
            "fracionamento": 0,
        }
    )
    assert iforest._motivo(despesa, atributo, 1000.0).startswith("Combinação incomum")


def test_poucas_despesas_nao_treina_o_modelo():
    resultado = iforest.detectar(montar_despesas([{"valor": 100.0}] * 5))
    assert not resultado["sinalizado"].any()
    assert (resultado["score"] == 0).all()


def test_sem_despesas():
    resultado = iforest.detectar(pd.DataFrame(columns=["despesa_id", "valor", "data", "categoria"]))
    assert resultado.empty
    assert tuple(resultado.columns) == COLUNAS_RESULTADO
