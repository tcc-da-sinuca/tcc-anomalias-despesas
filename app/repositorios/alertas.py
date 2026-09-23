"""Consultas de alertas e execuções de análise."""

from sqlalchemy import case, func, select
from sqlalchemy.orm import joinedload, selectinload

from app.extensoes import db
from app.models import AlertaAnomalia, ExecucaoAnalise
from app.models.dominio import STATUS_PENDENTE

POR_PAGINA_PADRAO = 50
POR_PAGINA_MAXIMO = 200


def paginar_alertas(
    pagina: int = 1,
    por_pagina: int = POR_PAGINA_PADRAO,
    *,
    status: str | None = None,
    metodo: str | None = None,
    execucao_id: int | None = None,
):
    """Pendentes primeiro e, dentro de cada status, maior score primeiro. Retorna um ``Pagination``.

    Os filtros combináveis da US10 (período, categoria etc.) entram na Sprint 4.
    """
    por_pagina = max(1, min(por_pagina, POR_PAGINA_MAXIMO))
    consulta = select(AlertaAnomalia).options(joinedload(AlertaAnomalia.despesa))
    if status:
        consulta = consulta.where(AlertaAnomalia.status_revisao == status)
    if metodo:
        consulta = consulta.where(AlertaAnomalia.metodo == metodo)
    if execucao_id is not None:
        consulta = consulta.where(AlertaAnomalia.execucao_id == execucao_id)
    pendente_primeiro = case((AlertaAnomalia.status_revisao == STATUS_PENDENTE, 0), else_=1)
    consulta = consulta.order_by(pendente_primeiro, AlertaAnomalia.score.desc(), AlertaAnomalia.id)
    return db.paginate(consulta, page=max(pagina, 1), per_page=por_pagina, error_out=False)


def obter_alerta(alerta_id: int) -> AlertaAnomalia | None:
    """Alerta com a despesa, a execução e os pareceres já carregados."""
    consulta = (
        select(AlertaAnomalia)
        .where(AlertaAnomalia.id == alerta_id)
        .options(
            joinedload(AlertaAnomalia.despesa),
            joinedload(AlertaAnomalia.execucao),
            selectinload(AlertaAnomalia.pareceres),
        )
    )
    return db.session.scalar(consulta)


def outros_alertas_da_despesa(alerta: AlertaAnomalia) -> list[AlertaAnomalia]:
    """Alertas de outros métodos para a mesma despesa."""
    consulta = (
        select(AlertaAnomalia)
        .where(AlertaAnomalia.despesa_id == alerta.despesa_id, AlertaAnomalia.id != alerta.id)
        .order_by(AlertaAnomalia.criado_em, AlertaAnomalia.metodo)
    )
    return list(db.session.scalars(consulta))


def paginar_execucoes(pagina: int = 1, por_pagina: int = 20):
    consulta = select(ExecucaoAnalise).order_by(
        ExecucaoAnalise.iniciada_em.desc(), ExecucaoAnalise.id.desc()
    )
    return db.paginate(consulta, page=max(pagina, 1), per_page=por_pagina, error_out=False)


def alertas_por_metodo(execucao_id: int) -> dict[str, int]:
    """Quantos alertas a execução criou em cada método."""
    consulta = (
        select(AlertaAnomalia.metodo, func.count(AlertaAnomalia.id))
        .where(AlertaAnomalia.execucao_id == execucao_id)
        .group_by(AlertaAnomalia.metodo)
        .order_by(AlertaAnomalia.metodo)
    )
    return dict(db.session.execute(consulta).all())
