"""Regra contextual: combinação categoria × conta contábil × centro de custo (RF05 / US05).

A frequência de uma combinação é medida dentro da categoria: despesas com a mesma
categoria, conta e centro de custo ÷ despesas da categoria (decisão D2 de
docs/FLUXO_ANALISE.md). A despesa é sinalizada quando essa frequência fica abaixo
do mínimo (padrão 1%). Uma combinação que não aparece em nenhuma outra despesa da
categoria ("inexistente no histórico") é o caso extremo.

Score = 1 - frequência, entre 0 e 1.
"""

import pandas as pd

from motor import texto
from motor.contrato import montar_resultado, resultado_vazio

COMBINACAO = ("categoria", "conta_contabil", "centro_custo")


def detectar(despesas: pd.DataFrame, frequencia_minima: float = 0.01) -> pd.DataFrame:
    """Frequência da combinação de cada despesa dentro da sua categoria. Ver ``motor.contrato``."""
    if despesas.empty:
        return resultado_vazio()

    na_combinacao = despesas.groupby(list(COMBINACAO))["despesa_id"].transform("size")
    na_categoria = despesas.groupby("categoria")["despesa_id"].transform("size")
    frequencia = na_combinacao / na_categoria
    sinalizado = frequencia < frequencia_minima

    motivos = pd.Series("", index=despesas.index, dtype=object)
    for i in despesas.index[sinalizado]:
        combinacao = (
            f"A combinação conta {despesas.at[i, 'conta_contabil']} × "
            f"centro de custo {despesas.at[i, 'centro_custo']}"
        )
        categoria = f"da categoria {despesas.at[i, 'categoria']}"
        if na_combinacao[i] == 1:
            motivos[i] = (
                f"{combinacao} não aparece em nenhuma outra despesa {categoria} "
                f"({texto.numero(na_categoria[i], 0)} despesas)."
            )
        else:
            motivos[i] = (
                f"{combinacao} aparece em {texto.percentual(frequencia[i])} das despesas "
                f"{categoria} ({na_combinacao[i]} de {texto.numero(na_categoria[i], 0)}); "
                f"mínimo {texto.percentual(frequencia_minima)}."
            )
    return montar_resultado(despesas, 1 - frequencia, sinalizado, motivos)
