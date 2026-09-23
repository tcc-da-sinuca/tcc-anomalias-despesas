"""Executa os detectores e junta os resultados em alertas (docs/FLUXO_ANALISE.md, seção 2.3).

``executar_detectores`` devolve o resultado completo de cada método (usado pelo
experimento, que precisa das despesas não sinalizadas). ``consolidar`` fica só
com as sinalizadas: um alerta por despesa e método.
"""

from collections.abc import Iterable

import pandas as pd

from motor import contextual, iqr, zscore

# O Isolation Forest entra na Sprint 3.
DETECTORES = {
    "zscore": zscore.detectar,
    "iqr": iqr.detectar,
    "contextual": contextual.detectar,
}
COLUNAS_ALERTA = ("despesa_id", "metodo", "score", "motivo")


class MetodoDesconhecidoError(ValueError):
    """Método sem detector implementado."""


def executar_detectores(
    despesas: pd.DataFrame,
    parametros: dict[str, dict[str, float | int]],
    metodos: Iterable[str] | None = None,
) -> dict[str, pd.DataFrame]:
    """Roda cada detector e devolve ``{metodo: DataFrame[despesa_id, score, sinalizado, motivo]}``.

    ``parametros[metodo]`` vira os argumentos do detector (ex.: ``{"limiar": 3.0}``).
    ``metodos`` vazio (``None``) roda todos os de ``DETECTORES``.
    """
    metodos = list(DETECTORES) if metodos is None else list(metodos)
    desconhecidos = [m for m in metodos if m not in DETECTORES]
    if desconhecidos:
        raise MetodoDesconhecidoError(
            f"Método(s) sem detector: {', '.join(desconhecidos)}. "
            f"Disponíveis: {', '.join(DETECTORES)}."
        )
    return {m: DETECTORES[m](despesas, **parametros.get(m, {})) for m in metodos}


def consolidar(resultados: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Só as linhas sinalizadas: DataFrame[despesa_id, metodo, score, motivo]."""
    partes = [
        resultado.loc[resultado["sinalizado"], ["despesa_id", "score", "motivo"]].assign(
            metodo=metodo
        )
        for metodo, resultado in resultados.items()
    ]
    partes = [p for p in partes if not p.empty]
    if not partes:
        return pd.DataFrame({c: pd.Series(dtype=object) for c in COLUNAS_ALERTA})
    alertas = pd.concat(partes, ignore_index=True)[list(COLUNAS_ALERTA)]
    return alertas.sort_values(["despesa_id", "metodo"], ignore_index=True)
