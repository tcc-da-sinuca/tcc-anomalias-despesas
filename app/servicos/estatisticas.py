"""Serviço de estatísticas de referência (RF02 / US02).

Recalcula as estatísticas de todas as despesas e substitui as anteriores. É
chamado após cada importação e cada cadastro manual.
"""

from decimal import ROUND_HALF_UP, Decimal

import pandas as pd
from sqlalchemy import delete, insert, select

from app.extensoes import db
from app.models import Despesa, EstatisticaReferencia
from app.models.base import agora_utc
from app.models.dominio import DIMENSOES
from motor.estatisticas import calcular_estatisticas

_QUATRO_CASAS = Decimal("0.0001")


def _decimal(valor) -> Decimal | None:
    if valor is None:
        return None
    return Decimal(str(valor)).quantize(_QUATRO_CASAS, ROUND_HALF_UP)


def recalcular_estatisticas() -> int:
    """Recalcula as estatísticas de todas as dimensões. Retorna quantos grupos gravou.

    Não faz commit.
    """
    colunas = ["valor", *DIMENSOES]
    linhas = db.session.execute(select(*(getattr(Despesa, c) for c in colunas))).all()
    estatisticas = calcular_estatisticas(pd.DataFrame(linhas, columns=colunas), DIMENSOES)

    db.session.execute(delete(EstatisticaReferencia))
    agora = agora_utc()
    registros = [
        {
            "dimensao": linha["dimensao"],
            "chave": linha["chave"],
            "media": _decimal(linha["media"]),
            "desvio": _decimal(linha["desvio"]),
            "q1": _decimal(linha["q1"]),
            "q3": _decimal(linha["q3"]),
            "n": int(linha["n"]),
            "calculada_em": agora,
        }
        for linha in estatisticas.to_dict("records")
    ]
    if registros:
        db.session.execute(insert(EstatisticaReferencia), registros)
    return len(registros)


def listar_estatisticas() -> dict[str, list[EstatisticaReferencia]]:
    """Estatísticas agrupadas por dimensão, na ordem de ``DIMENSOES``."""
    por_dimensao: dict[str, list[EstatisticaReferencia]] = {d: [] for d in DIMENSOES}
    consulta = select(EstatisticaReferencia).order_by(
        EstatisticaReferencia.dimensao, EstatisticaReferencia.chave
    )
    for estatistica in db.session.scalars(consulta):
        por_dimensao.setdefault(estatistica.dimensao, []).append(estatistica)
    return por_dimensao


def obter_estatistica(dimensao: str, chave: str) -> EstatisticaReferencia | None:
    """Estatística de um grupo, por exemplo ("categoria", "Viagens")."""
    return db.session.scalar(
        select(EstatisticaReferencia).where(
            EstatisticaReferencia.dimensao == dimensao, EstatisticaReferencia.chave == chave
        )
    )
