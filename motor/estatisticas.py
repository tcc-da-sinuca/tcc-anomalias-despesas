"""Estatísticas de referência por grupo de despesas (RF02 / US02).

Função pura: recebe um DataFrame e devolve as estatísticas de cada grupo. É
usada pelo serviço de estatísticas (que grava ``EstatisticaReferencia``) e será
reaproveitada pelos detectores Z-score e IQR.
"""

import pandas as pd

DIMENSOES_PADRAO = ("categoria", "conta_contabil", "centro_custo")
COLUNAS_RESULTADO = ("dimensao", "chave", "media", "desvio", "q1", "q3", "n")


def calcular_estatisticas(
    despesas: pd.DataFrame, dimensoes: tuple[str, ...] = DIMENSOES_PADRAO
) -> pd.DataFrame:
    """Média, desvio padrão amostral, Q1, Q3 e n do valor, por grupo de cada dimensão.

    ``despesas`` precisa da coluna ``valor`` e de uma coluna para cada dimensão.
    Os quartis usam interpolação linear (o mesmo que QUARTIL.INC do Excel). O
    desvio fica ``None`` quando o grupo tem uma única despesa.
    """
    if despesas.empty:
        return pd.DataFrame(columns=list(COLUNAS_RESULTADO))

    valores = despesas["valor"].astype(float)
    partes = []
    for dimensao in dimensoes:
        grupos = valores.groupby(despesas[dimensao])
        resultado = pd.DataFrame(
            {
                "media": grupos.mean(),
                "desvio": grupos.std(ddof=1),
                "q1": grupos.quantile(0.25),
                "q3": grupos.quantile(0.75),
                "n": grupos.size(),
            }
        )
        resultado.index.name = "chave"
        resultado = resultado.reset_index()
        resultado.insert(0, "dimensao", dimensao)
        partes.append(resultado)

    estatisticas = pd.concat(partes, ignore_index=True)
    estatisticas["desvio"] = estatisticas["desvio"].astype(object)
    estatisticas.loc[estatisticas["desvio"].isna(), "desvio"] = None
    return estatisticas[list(COLUNAS_RESULTADO)]
