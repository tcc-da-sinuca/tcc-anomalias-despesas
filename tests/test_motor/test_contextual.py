"""Regra contextual: categoria × conta × centro de custo (US05)."""

import pandas as pd
import pytest

from motor import contextual
from motor.contrato import COLUNAS_RESULTADO
from tests.test_motor.auxiliares import montar_despesas


def _combinacoes(*grupos):
    """grupos: (quantidade, categoria, conta, centro de custo)."""
    linhas = []
    for quantidade, categoria, conta, centro in grupos:
        linhas += [
            {
                "valor": 100.0,
                "categoria": categoria,
                "conta_contabil": conta,
                "centro_custo": centro,
            }
        ] * quantidade
    return montar_despesas(linhas)


def test_combinacao_inexistente_no_historico():
    despesas = _combinacoes((199, "Viagens", "3.1", "CC-ADM"), (1, "Viagens", "3.1", "CC-TI"))
    resultado = contextual.detectar(despesas)

    assert resultado["sinalizado"].tolist() == [False] * 199 + [True]
    assert resultado["score"].iloc[-1] == pytest.approx(1 - 1 / 200)
    assert resultado["motivo"].iloc[-1] == (
        "A combinação conta 3.1 × centro de custo CC-TI não aparece em nenhuma outra "
        "despesa da categoria Viagens (200 despesas)."
    )


def test_combinacao_rara():
    despesas = _combinacoes((297, "Viagens", "3.1", "CC-ADM"), (3, "Viagens", "3.1", "CC-TI"))
    resultado = contextual.detectar(despesas, frequencia_minima=0.02)

    assert resultado["sinalizado"].sum() == 3
    assert resultado["motivo"].iloc[-1] == (
        "A combinação conta 3.1 × centro de custo CC-TI aparece em 1% das despesas "
        "da categoria Viagens (3 de 300); mínimo 2%."
    )


def test_frequencia_e_medida_dentro_da_categoria():
    # Hospedagem tem só 5 despesas (1% do total), mas sempre na mesma combinação.
    despesas = _combinacoes(
        (495, "Alimentação", "3.2", "CC-ADM"), (5, "Hospedagem", "3.3", "CC-COM")
    )
    assert not contextual.detectar(despesas)["sinalizado"].any()


def test_combinacao_comum_nao_sinaliza():
    despesas = _combinacoes((60, "Viagens", "3.1", "CC-ADM"), (40, "Viagens", "3.1", "CC-TI"))
    resultado = contextual.detectar(despesas)

    assert not resultado["sinalizado"].any()
    assert (resultado["motivo"] == "").all()


def test_sem_despesas():
    colunas = ["despesa_id", "valor", "categoria", "conta_contabil", "centro_custo"]
    resultado = contextual.detectar(pd.DataFrame(columns=colunas))
    assert resultado.empty
    assert tuple(resultado.columns) == COLUNAS_RESULTADO
