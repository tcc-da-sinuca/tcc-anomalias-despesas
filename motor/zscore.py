"""Detector Z-score por grupo (RF03 / US03).

z = (valor - média do grupo) / desvio padrão amostral do grupo. O score é |z| e a
despesa é sinalizada quando |z| passa do limiar (padrão 3). Grupos com menos de
``N_MINIMO_GRUPO`` despesas, ou com desvio zero, não são avaliados.
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
    limiar: float = 3.0,
    dimensao: str | tuple[str, ...] = DIMENSAO_DETECCAO,
    recuo: str | tuple[str, ...] | None = DIMENSAO_RECUO,
) -> pd.DataFrame:
    """Score |z| de cada despesa no seu grupo. Ver ``motor.contrato``."""
    if despesas.empty:
        return resultado_vazio()

    valores = despesas["valor"].astype(float)
    grupo = estatisticas_por_despesa(despesas, dimensao, recuo)
    avaliavel = (grupo["n"] >= N_MINIMO_GRUPO) & (grupo["desvio"] > 0)
    z = ((valores - grupo["media"]) / grupo["desvio"]).where(avaliavel, 0.0)
    score = z.abs()
    sinalizado = score > limiar

    motivos = pd.Series("", index=despesas.index, dtype=object)
    for i in despesas.index[sinalizado]:
        nome_grupo = descrever_grupo(despesas.loc[i], dimensao, recuo, grupo.at[i, "usa_recuo"])
        motivos[i] = _motivo(valores[i], grupo.at[i, "media"], z[i], limiar, nome_grupo)
    return montar_resultado(despesas, score, sinalizado, motivos, score / limiar)


def _motivo(valor, media, z, limiar, nome_grupo) -> str:
    referencia = f"média {nome_grupo} ({texto.moeda(media)})"
    if z > 0:
        comparacao = f"é {texto.numero(valor / media)}x a {referencia}"
    else:
        comparacao = f"está muito abaixo da {referencia}"
    return (
        f"Valor {texto.moeda(valor)} {comparacao}; "
        f"z = {texto.numero(z)}, limiar {texto.numero(limiar)}."
    )
