"""Indicadores do dashboard (RF09 / US09).

- total de despesas (quantidade e valor);
- total sinalizado: despesas **distintas** com pelo menos um alerta, porque uma
  despesa pode ser sinalizada por vários métodos;
- % sinalizado: despesas sinalizadas ÷ total de despesas;
- alertas por status de revisão (e por método, para contexto).
"""

from decimal import Decimal

from sqlalchemy import func, select

from app.extensoes import db
from app.models import AlertaAnomalia, Despesa, ExecucaoAnalise
from app.models.dominio import METODOS, STATUS_REVISAO


def resumo() -> dict:
    """Indicadores atuais. Valores monetários em ``Decimal``; percentual entre 0 e 100."""
    total_despesas, valor_despesas = db.session.execute(
        select(func.count(Despesa.id), func.coalesce(func.sum(Despesa.valor), 0))
    ).one()

    sinalizadas = select(AlertaAnomalia.despesa_id).distinct().subquery()
    despesas_sinalizadas, valor_sinalizado = db.session.execute(
        select(func.count(Despesa.id), func.coalesce(func.sum(Despesa.valor), 0)).where(
            Despesa.id.in_(select(sinalizadas.c.despesa_id))
        )
    ).one()

    por_status = dict.fromkeys(STATUS_REVISAO, 0)
    por_status.update(
        db.session.execute(
            select(AlertaAnomalia.status_revisao, func.count(AlertaAnomalia.id)).group_by(
                AlertaAnomalia.status_revisao
            )
        ).all()
    )
    por_metodo = dict.fromkeys(METODOS, 0)
    por_metodo.update(
        db.session.execute(
            select(AlertaAnomalia.metodo, func.count(AlertaAnomalia.id)).group_by(
                AlertaAnomalia.metodo
            )
        ).all()
    )
    ultima_analise = db.session.scalar(
        select(ExecucaoAnalise).order_by(
            ExecucaoAnalise.iniciada_em.desc(), ExecucaoAnalise.id.desc()
        )
    )

    return {
        "total_despesas": total_despesas,
        "valor_despesas": Decimal(valor_despesas),
        "despesas_sinalizadas": despesas_sinalizadas,
        "valor_sinalizado": Decimal(valor_sinalizado),
        "percentual_sinalizado": (
            round(100 * despesas_sinalizadas / total_despesas, 2) if total_despesas else 0.0
        ),
        "total_alertas": sum(por_status.values()),
        "alertas_por_status": por_status,
        "alertas_por_metodo": por_metodo,
        "ultima_analise": ultima_analise,
    }
