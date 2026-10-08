"""Contrato comum dos detectores (docs/FLUXO_ANALISE.md, seção 2.1).

Entrada: DataFrame com ``despesa_id``, ``valor``, ``data``, ``categoria``,
``conta_contabil``, ``centro_custo`` e ``funcionario``.

Saída: DataFrame[despesa_id, score, sinalizado, motivo, excesso], com uma linha
por despesa, sinalizada ou não. O score cresce com o grau de anomalia e tem a escala
do próprio método. O motivo só é preenchido nas linhas sinalizadas. O excesso é o
score dividido pelo limite do método (≥ 1 nas sinalizadas; ver ``motor.gravidade``).
"""

import pandas as pd

COLUNAS_ENTRADA = (
    "despesa_id",
    "valor",
    "data",
    "categoria",
    "conta_contabil",
    "centro_custo",
    "funcionario",
)
COLUNAS_RESULTADO = ("despesa_id", "score", "sinalizado", "motivo", "excesso")


def montar_resultado(
    despesas: pd.DataFrame,
    score: pd.Series,
    sinalizado: pd.Series,
    motivo: pd.Series,
    excesso: pd.Series,
) -> pd.DataFrame:
    """Junta as colunas do resultado, com tipos fixos e motivo vazio onde não sinalizou."""
    sinalizado = sinalizado.astype(bool)
    return pd.DataFrame(
        {
            "despesa_id": despesas["despesa_id"].to_numpy(),
            "score": score.astype(float).to_numpy(),
            "sinalizado": sinalizado.to_numpy(),
            "motivo": motivo.where(sinalizado, "").to_numpy(dtype=object),
            "excesso": excesso.astype(float).to_numpy(),
        }
    )


def resultado_vazio() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "despesa_id": pd.Series(dtype="int64"),
            "score": pd.Series(dtype="float64"),
            "sinalizado": pd.Series(dtype="bool"),
            "motivo": pd.Series(dtype="object"),
            "excesso": pd.Series(dtype="float64"),
        }
    )
