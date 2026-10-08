"""Estatísticas de referência por grupo de despesas (RF02 / US02).

Função pura: recebe um DataFrame e devolve as estatísticas de cada grupo. É
usada pelo serviço de estatísticas (que grava ``EstatisticaReferencia``) e será
reaproveitada pelos detectores Z-score e IQR.
"""

import pandas as pd

DIMENSOES_PADRAO = ("categoria", "conta_contabil", "centro_custo")
COLUNAS_RESULTADO = ("dimensao", "chave", "media", "desvio", "q1", "q3", "n")

# Referência do Z-score, do IQR e do desvio de valor do Isolation Forest: o histórico
# do centro de custo × conta contábil (decisão da equipe em 08/10/2026, item 32 de
# MUDANCAS_PARA_DOCUMENTACAO.md). Grupo com menos de N_MINIMO_GRUPO despesas usa a
# categoria como recuo; se ela também for pequena, a despesa não é avaliada (decisão D4).
DIMENSAO_DETECCAO = ("centro_custo", "conta_contabil")
DIMENSAO_RECUO = "categoria"
N_MINIMO_GRUPO = 10


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


def colunas_da_dimensao(dimensao: str | tuple[str, ...]) -> list[str]:
    """ "categoria" → ["categoria"]; ("centro_custo", "conta_contabil") → as duas colunas."""
    return [dimensao] if isinstance(dimensao, str) else list(dimensao)


def _estatisticas_do_grupo(despesas: pd.DataFrame, colunas: list[str]) -> pd.DataFrame:
    grupos = despesas["valor"].astype(float).groupby([despesas[c] for c in colunas])
    return pd.DataFrame(
        {
            "media": grupos.transform("mean"),
            "desvio": grupos.transform("std"),
            "q1": grupos.transform(lambda valores: valores.quantile(0.25)),
            "q3": grupos.transform(lambda valores: valores.quantile(0.75)),
            "n": grupos.transform("size"),
        },
        index=despesas.index,
    )


def estatisticas_por_despesa(
    despesas: pd.DataFrame,
    dimensao: str | tuple[str, ...],
    recuo: str | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Estatísticas do grupo de cada despesa, alinhadas ao índice de ``despesas``.

    Devolve ``media``, ``desvio``, ``q1``, ``q3`` e ``n`` (mesmas regras de
    ``calcular_estatisticas``; desvio ``NaN`` em grupo de uma despesa) e ``usa_recuo``.
    Com ``recuo``, a despesa cujo grupo tem menos de ``N_MINIMO_GRUPO`` despesas usa as
    estatísticas do grupo de recuo (``usa_recuo`` verdadeiro).
    """
    estatisticas = _estatisticas_do_grupo(despesas, colunas_da_dimensao(dimensao))
    estatisticas["usa_recuo"] = False
    if recuo is not None:
        pequeno = estatisticas["n"] < N_MINIMO_GRUPO
        if pequeno.any():
            do_recuo = _estatisticas_do_grupo(despesas, colunas_da_dimensao(recuo))
            colunas = ["media", "desvio", "q1", "q3", "n"]
            estatisticas.loc[pequeno, colunas] = do_recuo.loc[pequeno, colunas]
            estatisticas.loc[pequeno, "usa_recuo"] = True
    return estatisticas


def descrever_grupo(despesa: pd.Series, dimensao, recuo, usa_recuo: bool) -> str:
    """Texto do grupo de referência de uma despesa, para o motivo."""
    from motor import texto

    escolhida = recuo if usa_recuo and recuo is not None else dimensao
    colunas = colunas_da_dimensao(escolhida)
    return texto.grupo(tuple(colunas), tuple(despesa[c] for c in colunas))
