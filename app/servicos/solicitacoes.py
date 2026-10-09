"""Pedidos de aprovação de despesas lançadas fora do padrão (item 34 de MUDANCAS).

Regras:

- só o **administrador** aprova ou rejeita, e **nunca o próprio pedido** (segregação de
  funções: quem lançou a despesa não decide sobre ela);
- aprovar: a despesa vira válida; os alertas dela recebem o parecer "aprovado";
- rejeitar (justificativa obrigatória): a despesa fica rejeitada; os alertas recebem o
  parecer "irregular";
- um pedido rejeitado automaticamente (alerta de gravidade crítica) pode ser
  **encaminhado** por quem lançou ou por um administrador, com justificativa: volta a
  ficar pendente, como **prioritário**;
- cada passo vira um ``EventoSolicitacao`` (somente inserção).

Não faz commit.
"""

from sqlalchemy import case, func, select
from sqlalchemy.orm import joinedload, selectinload

from app.extensoes import db
from app.models import Despesa, EventoSolicitacao, SolicitacaoAprovacao, Usuario
from app.models.base import agora_utc
from app.models.dominio import (
    EVENTO_APROVADA,
    EVENTO_ENCAMINHADA,
    EVENTO_REJEITADA,
    PERFIL_ADMINISTRADOR,
    SITUACAO_REJEITADA,
    SITUACAO_VALIDA,
    SOLICITACAO_APROVADA,
    SOLICITACAO_PENDENTE,
    SOLICITACAO_REJEITADA,
    SOLICITACAO_REJEITADA_AUTOMATICAMENTE,
    STATUS_APROVADO,
    STATUS_IRREGULAR,
    STATUS_SOLICITACAO,
)
from app.servicos.estatisticas import recalcular_estatisticas
from app.servicos.revisao import registrar_parecer

POR_PAGINA_PADRAO = 30


class SolicitacaoInvalidaError(ValueError):
    """Operação não permitida no estado atual do pedido ou para este usuário."""


def _texto(valor: str | None) -> str | None:
    return (valor or "").strip() or None


def _registrar_evento(solicitacao, tipo, usuario: Usuario | None, observacao=None) -> None:
    db.session.add(
        EventoSolicitacao(
            solicitacao_id=solicitacao.id,
            tipo=tipo,
            usuario_id=usuario.id if usuario else None,
            observacao=observacao,
        )
    )


def _exigir_decisor(solicitacao: SolicitacaoAprovacao, usuario: Usuario) -> None:
    if usuario.perfil != PERFIL_ADMINISTRADOR:
        raise SolicitacaoInvalidaError("Só o administrador aprova ou rejeita pedidos.")
    if solicitacao.solicitada_por == usuario.id:
        raise SolicitacaoInvalidaError(
            "Você lançou esta despesa e não pode decidir o próprio pedido. "
            "Peça a outro administrador."
        )
    if solicitacao.status != SOLICITACAO_PENDENTE:
        raise SolicitacaoInvalidaError("Este pedido não está pendente.")


def _decidir(solicitacao, usuario, status, justificativa) -> None:
    solicitacao.status = status
    solicitacao.decidida_por = usuario.id
    solicitacao.decidida_em = agora_utc()
    solicitacao.justificativa = justificativa


def aprovar(solicitacao: SolicitacaoAprovacao, usuario: Usuario, observacao: str | None = None):
    """A despesa passa a ser válida; os alertas dela recebem o parecer "aprovado"."""
    _exigir_decisor(solicitacao, usuario)
    observacao = _texto(observacao)
    _decidir(solicitacao, usuario, SOLICITACAO_APROVADA, observacao)
    solicitacao.despesa.situacao = SITUACAO_VALIDA
    _registrar_evento(solicitacao, EVENTO_APROVADA, usuario, observacao)
    for alerta in solicitacao.despesa.alertas:
        registrar_parecer(
            alerta,
            usuario,
            STATUS_APROVADO,
            f"Despesa aprovada no pedido #{solicitacao.id}."
            + (f" {observacao}" if observacao else ""),
        )
    db.session.flush()
    recalcular_estatisticas()


def rejeitar(solicitacao: SolicitacaoAprovacao, usuario: Usuario, justificativa: str | None):
    """A despesa fica rejeitada; os alertas dela recebem o parecer "irregular"."""
    _exigir_decisor(solicitacao, usuario)
    justificativa = _texto(justificativa)
    if justificativa is None:
        raise SolicitacaoInvalidaError("Informe a justificativa da rejeição.")
    _decidir(solicitacao, usuario, SOLICITACAO_REJEITADA, justificativa)
    solicitacao.despesa.situacao = SITUACAO_REJEITADA
    _registrar_evento(solicitacao, EVENTO_REJEITADA, usuario, justificativa)
    for alerta in solicitacao.despesa.alertas:
        registrar_parecer(
            alerta,
            usuario,
            STATUS_IRREGULAR,
            f"Pedido #{solicitacao.id} rejeitado: {justificativa}",
        )


def pode_encaminhar(solicitacao: SolicitacaoAprovacao, usuario: Usuario) -> bool:
    return solicitacao.status == SOLICITACAO_REJEITADA_AUTOMATICAMENTE and (
        usuario.id == solicitacao.solicitada_por or usuario.perfil == PERFIL_ADMINISTRADOR
    )


def pode_decidir(solicitacao: SolicitacaoAprovacao, usuario: Usuario) -> bool:
    try:
        _exigir_decisor(solicitacao, usuario)
    except SolicitacaoInvalidaError:
        return False
    return True


def encaminhar(solicitacao: SolicitacaoAprovacao, usuario: Usuario, justificativa: str | None):
    """Pedido rejeitado automaticamente volta a ficar pendente, como prioritário."""
    if solicitacao.status != SOLICITACAO_REJEITADA_AUTOMATICAMENTE:
        raise SolicitacaoInvalidaError(
            "Só pedidos rejeitados automaticamente podem ser encaminhados."
        )
    if not pode_encaminhar(solicitacao, usuario):
        raise SolicitacaoInvalidaError(
            "Só quem lançou a despesa ou um administrador pode encaminhar."
        )
    justificativa = _texto(justificativa)
    if justificativa is None:
        raise SolicitacaoInvalidaError("Explique por que a despesa deve ser reavaliada.")
    solicitacao.status = SOLICITACAO_PENDENTE
    solicitacao.prioritaria = True
    _registrar_evento(solicitacao, EVENTO_ENCAMINHADA, usuario, justificativa)


# --- Consultas -------------------------------------------------------------------


def paginar(status: str | None = None, pagina: int = 1, por_pagina: int = POR_PAGINA_PADRAO):
    """Pedidos do mais urgente para o menos: pendentes prioritários, pendentes, depois os demais.

    Dentro de cada grupo, gravidade mais alta e mais recentes primeiro.
    """
    if status is not None and status not in STATUS_SOLICITACAO:
        raise SolicitacaoInvalidaError(
            f"status inválido. Use um de: {', '.join(STATUS_SOLICITACAO)}."
        )
    consulta = select(SolicitacaoAprovacao).options(
        joinedload(SolicitacaoAprovacao.despesa), joinedload(SolicitacaoAprovacao.solicitante)
    )
    if status:
        consulta = consulta.where(SolicitacaoAprovacao.status == status)
    urgencia = case(
        (
            (SolicitacaoAprovacao.status == SOLICITACAO_PENDENTE)
            & SolicitacaoAprovacao.prioritaria,
            0,
        ),
        (SolicitacaoAprovacao.status == SOLICITACAO_PENDENTE, 1),
        else_=2,
    )
    peso_gravidade = case(
        (SolicitacaoAprovacao.gravidade == "critica", 0),
        (SolicitacaoAprovacao.gravidade == "alta", 1),
        (SolicitacaoAprovacao.gravidade == "moderada", 2),
        else_=3,
    )
    consulta = consulta.order_by(
        urgencia,
        peso_gravidade,
        SolicitacaoAprovacao.criada_em.desc(),
        SolicitacaoAprovacao.id.desc(),
    )
    return db.paginate(consulta, page=max(pagina, 1), per_page=por_pagina, error_out=False)


def obter(solicitacao_id: int) -> SolicitacaoAprovacao | None:
    consulta = (
        select(SolicitacaoAprovacao)
        .where(SolicitacaoAprovacao.id == solicitacao_id)
        .options(
            joinedload(SolicitacaoAprovacao.despesa).selectinload(Despesa.alertas),
            selectinload(SolicitacaoAprovacao.eventos),
        )
    )
    return db.session.scalar(consulta)


def contar_por_status() -> dict[str, int]:
    """Quantidade de pedidos em cada status, mais os pendentes prioritários."""
    contagem = dict.fromkeys(STATUS_SOLICITACAO, 0)
    contagem.update(
        db.session.execute(
            select(SolicitacaoAprovacao.status, func.count(SolicitacaoAprovacao.id)).group_by(
                SolicitacaoAprovacao.status
            )
        ).all()
    )
    contagem["prioritarios"] = db.session.scalar(
        select(func.count(SolicitacaoAprovacao.id)).where(
            SolicitacaoAprovacao.status == SOLICITACAO_PENDENTE, SolicitacaoAprovacao.prioritaria
        )
    )
    return contagem
