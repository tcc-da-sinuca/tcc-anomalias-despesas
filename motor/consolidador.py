"""Executa os detectores e junta os resultados em alertas (docs/FLUXO_ANALISE.md, seção 2.3).

``executar_detectores`` devolve o resultado completo de cada método (usado pelo
experimento, que precisa das despesas não sinalizadas). ``consolidar`` fica só
com as sinalizadas: um alerta por despesa e método.
"""

import inspect
from collections.abc import Iterable

import pandas as pd

from motor import contextual, iqr, isolation_forest, zscore
from motor.gravidade import classificar

DETECTORES = {
    "zscore": zscore.detectar,
    "iqr": iqr.detectar,
    "contextual": contextual.detectar,
    "isolation_forest": isolation_forest.detectar,
}
COLUNAS_ALERTA = ("despesa_id", "metodo", "score", "motivo", "excesso", "gravidade")


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


def parametros_padrao(metodos: Iterable[str] | None = None) -> dict[str, dict[str, float | int]]:
    """Valores padrão dos parâmetros de cada detector, lidos da assinatura da função.

    Usado pelo experimento, que roda sem banco. Na aplicação os valores vêm de
    ``ParametroMetodo``; um teste garante que os dois coincidem.
    """
    metodos = list(DETECTORES) if metodos is None else list(metodos)
    padroes = {}
    for metodo in metodos:
        assinatura = inspect.signature(DETECTORES[metodo])
        padroes[metodo] = {
            nome: p.default
            for nome, p in list(assinatura.parameters.items())[1:]
            if nome not in ("dimensao", "recuo")
        }
    return padroes


def consolidar(resultados: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Só as linhas sinalizadas, com a gravidade de cada uma (``COLUNAS_ALERTA``)."""
    partes = []
    for metodo, resultado in resultados.items():
        sinalizadas = resultado.loc[
            resultado["sinalizado"], ["despesa_id", "score", "motivo", "excesso"]
        ]
        partes.append(
            sinalizadas.assign(
                metodo=metodo,
                gravidade=[classificar(metodo, e) for e in sinalizadas["excesso"]],
            )
        )
    partes = [p for p in partes if not p.empty]
    if not partes:
        return pd.DataFrame({c: pd.Series(dtype=object) for c in COLUNAS_ALERTA})
    alertas = pd.concat(partes, ignore_index=True)[list(COLUNAS_ALERTA)]
    return alertas.sort_values(["despesa_id", "metodo"], ignore_index=True)
