"""Detector IQR (US03)."""

import pandas as pd
import pytest

from motor import iqr
from motor.contrato import COLUNAS_RESULTADO
from tests.test_motor.auxiliares import grupo_com_extremo, montar_despesas


def _valores(valores, categoria="Viagens"):
    return montar_despesas([{"valor": v, "categoria": categoria} for v in valores])


def test_score_em_iqrs_calculado_a_mao():
    # 1..11 e 40: Q1 = 3,75; Q3 = 9,25; IQR = 5,5 (interpolação linear).
    despesas = _valores([float(v) for v in range(1, 12)] + [40.0])
    resultado = iqr.detectar(despesas)

    assert resultado["score"].iloc[-1] == pytest.approx((40 - 9.25) / 5.5)
    # 1 fica fora da caixa, mas dentro do limite
    assert resultado["score"].iloc[0] == pytest.approx((3.75 - 1) / 5.5)
    assert resultado["score"].iloc[5] == 0  # 6 está dentro da caixa Q1–Q3
    assert resultado["sinalizado"].tolist() == [False] * 11 + [True]


def test_motivo_com_o_limite_do_grupo():
    despesas = _valores([float(v) for v in range(1, 12)] + [40.0])
    motivo = iqr.detectar(despesas)["motivo"].iloc[-1]

    # limite superior = 9,25 + 1,5 × 5,5 = 17,50
    assert motivo == (
        "Valor R$ 40,00 acima do limite superior da categoria Viagens (Q3 + 1,5 × IQR = R$ 17,50)."
    )


def test_valor_abaixo_do_limite_inferior():
    despesas = _valores([100.0 + v for v in range(12)] + [2.0])
    resultado = iqr.detectar(despesas)

    assert resultado["sinalizado"].iloc[-1]
    assert "abaixo do limite inferior" in resultado["motivo"].iloc[-1]


def test_fator_configuravel():
    despesas = _valores([float(v) for v in range(1, 12)] + [40.0])
    assert not iqr.detectar(despesas, fator=6.0)["sinalizado"].any()


def test_grupo_pequeno_ou_sem_variacao_nao_e_avaliado():
    pequeno = iqr.detectar(montar_despesas(grupo_com_extremo(n_normais=5)))
    constante = iqr.detectar(_valores([50.0] * 15))

    assert (pequeno["score"] == 0).all()
    assert (constante["score"] == 0).all()


def test_sem_despesas():
    resultado = iqr.detectar(pd.DataFrame(columns=["despesa_id", "valor", "categoria"]))
    assert resultado.empty
    assert tuple(resultado.columns) == COLUNAS_RESULTADO
