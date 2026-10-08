"""Detector IQR (amplitude interquartil) por grupo (RF03 / US03).

Limites do grupo: Q1 - fator × IQR e Q3 + fator × IQR (fator padrão 1,5). O score é
a distância do valor além do quartil mais próximo, medida em IQRs (0 dentro da
caixa Q1–Q3). Assim, "score > fator" equivale a "fora dos limites". Grupos com
menos de ``N_MINIMO_GRUPO`` despesas, ou com IQR zero, não são avaliados.
"""

import pandas as pd

from motor import texto
from motor.contrato import montar_resultado, resultado_vazio
from motor.estatisticas import (
    DIMENSAO_DETECCAO,
    DIMENSAO_RECUO,
    N_MINIMO_GRUPO,
    descrever_grupo,
    estatisticas_por_despesa,
)


def detectar(
    despesas: pd.DataFrame,
    fator: float = 1.5,
    dimensao: str | tuple[str, ...] = DIMENSAO_DETECCAO,
    recuo: str | tuple[str, ...] | None = DIMENSAO_RECUO,
) -> pd.DataFrame:
    """Distância de cada despesa além dos quartis do seu grupo, em IQRs. Ver ``motor.contrato``."""
    if despesas.empty:
        return resultado_vazio()

    valores = despesas["valor"].astype(float)
    grupo = estatisticas_por_despesa(despesas, dimensao, recuo)
    iqr = grupo["q3"] - grupo["q1"]
    avaliavel = (grupo["n"] >= N_MINIMO_GRUPO) & (iqr > 0)
    acima = (valores - grupo["q3"]) / iqr
    abaixo = (grupo["q1"] - valores) / iqr
    score = pd.concat([acima, abaixo], axis=1).max(axis=1).clip(lower=0).where(avaliavel, 0.0)
    sinalizado = score > fator

    motivos = pd.Series("", index=despesas.index, dtype=object)
    for i in despesas.index[sinalizado]:
        nome_grupo = descrever_grupo(despesas.loc[i], dimensao, recuo, grupo.at[i, "usa_recuo"])
        f = texto.numero(fator)
        if acima[i] > 0:
            limite = grupo.at[i, "q3"] + fator * iqr[i]
            descricao = f"acima do limite superior {nome_grupo} (Q3 + {f} × IQR"
        else:
            limite = grupo.at[i, "q1"] - fator * iqr[i]
            descricao = f"abaixo do limite inferior {nome_grupo} (Q1 − {f} × IQR"
        motivos[i] = f"Valor {texto.moeda(valores[i])} {descricao} = {texto.moeda(limite)})."
    return montar_resultado(despesas, score, sinalizado, motivos, score / fator)
