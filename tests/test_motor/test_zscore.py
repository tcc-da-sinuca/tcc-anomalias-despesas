"""Detector Z-score (US03)."""

import pandas as pd
import pytest

from motor import zscore
from motor.contrato import COLUNAS_RESULTADO
from tests.test_motor.auxiliares import grupo_com_extremo, montar_despesas


def test_sinaliza_so_o_valor_extremo():
    despesas = montar_despesas(grupo_com_extremo())
    resultado = zscore.detectar(despesas)

    assert tuple(resultado.columns) == COLUNAS_RESULTADO
    assert len(resultado) == len(despesas)  # uma linha por despesa
    assert resultado["sinalizado"].tolist() == [False] * 20 + [True]
    assert (resultado.loc[~resultado["sinalizado"], "motivo"] == "").all()


def test_score_e_o_modulo_de_z_calculado_a_mao():
    despesas = montar_despesas(grupo_com_extremo())
    valores = despesas["valor"]
    z_esperado = (1000.0 - valores.mean()) / valores.std(ddof=1)

    resultado = zscore.detectar(despesas)

    assert resultado["score"].iloc[-1] == pytest.approx(abs(z_esperado))
    assert (resultado["score"] >= 0).all()


def test_motivo_legivel():
    despesas = montar_despesas(grupo_com_extremo())
    motivo = zscore.detectar(despesas)["motivo"].iloc[-1]

    assert motivo.startswith("Valor R$ 1.000,00 é ")
    assert "x a média da categoria Viagens (R$ " in motivo
    assert motivo.endswith("limiar 3.")


def test_valor_abaixo_da_media():
    linhas = [{"valor": 1000.0 + (i % 5)} for i in range(30)] + [{"valor": 10.0}]
    resultado = zscore.detectar(montar_despesas(linhas))

    assert resultado["sinalizado"].iloc[-1]
    assert "está muito abaixo da média" in resultado["motivo"].iloc[-1]


def test_limiar_configuravel():
    despesas = montar_despesas(grupo_com_extremo())
    score_extremo = zscore.detectar(despesas)["score"].iloc[-1]

    assert not zscore.detectar(despesas, limiar=score_extremo + 0.1)["sinalizado"].any()


def test_grupos_por_categoria_sao_independentes():
    # O mesmo valor é extremo em Alimentação e normal em Viagens.
    linhas = (
        grupo_com_extremo(extremo=500.0, categoria="Alimentação")
        + [{"valor": 450.0 + i * 10, "categoria": "Viagens"} for i in range(12)]
        + [{"valor": 500.0, "categoria": "Viagens"}]
    )
    resultado = zscore.detectar(montar_despesas(linhas))

    assert resultado["sinalizado"].sum() == 1
    assert resultado["sinalizado"].iloc[20]


def test_grupo_pequeno_nao_e_avaliado():
    despesas = montar_despesas(grupo_com_extremo(n_normais=8))  # 9 < N_MINIMO_GRUPO
    resultado = zscore.detectar(despesas)

    assert not resultado["sinalizado"].any()
    assert (resultado["score"] == 0).all()


def test_grupo_sem_variacao_nao_e_avaliado():
    resultado = zscore.detectar(montar_despesas([{"valor": 50.0}] * 15))
    assert (resultado["score"] == 0).all()


def test_outra_dimensao():
    linhas = [{"valor": 100.0 + (i % 7), "centro_custo": "CC-TI"} for i in range(15)]
    linhas.append({"valor": 900.0, "centro_custo": "CC-TI", "categoria": "Software"})
    resultado = zscore.detectar(montar_despesas(linhas), dimensao="centro_custo")

    assert resultado["sinalizado"].iloc[-1]
    assert "do centro de custo CC-TI" in resultado["motivo"].iloc[-1]


def test_sem_despesas():
    resultado = zscore.detectar(pd.DataFrame(columns=["despesa_id", "valor", "categoria"]))
    assert resultado.empty
    assert tuple(resultado.columns) == COLUNAS_RESULTADO
