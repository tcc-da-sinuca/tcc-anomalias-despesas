"""Aprovação prévia de despesas fora do padrão (item 34 de MUDANCAS_PARA_DOCUMENTACAO.md).

Quando uma despesa é lançada (cadastro ou importação), os métodos rodam na hora. Se
algum sinaliza, a despesa não entra como válida: abre-se um ``SolicitacaoAprovacao``
("ticket") para o administrador decidir. Com algum alerta de gravidade crítica, o
pedido é rejeitado automaticamente e pode ser encaminhado para decisão humana, com
prioridade.

``EventoSolicitacao`` é o histórico do pedido e é somente inserção, como o parecer:
eventos do SQLAlchemy aqui e trigger no PostgreSQL (migration 0003).
"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, event
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.extensoes import db
from app.models.base import agora_utc
from app.models.dominio import (
    SOLICITACAO_PENDENTE,
    SQL_GRAVIDADES,
    SQL_STATUS_SOLICITACAO,
    SQL_TIPOS_EVENTO,
)


class EventoImutavelError(Exception):
    """Tentativa de alterar ou remover um evento do histórico de um pedido."""


class SolicitacaoAprovacao(db.Model):
    """Pedido de aprovação de uma despesa lançada fora do padrão."""

    __tablename__ = "solicitacao_aprovacao"
    __table_args__ = (
        CheckConstraint(f"status IN {SQL_STATUS_SOLICITACAO}", name="status_valido"),
        CheckConstraint(
            f"gravidade IS NULL OR gravidade IN {SQL_GRAVIDADES}", name="gravidade_valida"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    despesa_id: Mapped[int] = mapped_column(
        ForeignKey("despesa.id"), nullable=False, unique=True, index=True
    )
    solicitada_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    criada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora_utc
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=SOLICITACAO_PENDENTE, index=True
    )
    # Gravidade mais alta entre os alertas da despesa (motor/gravidade.py).
    gravidade: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Encaminhada depois de uma rejeição automática: aparece em destaque e no topo da fila.
    prioritaria: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    decidida_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    decidida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    justificativa: Mapped[str | None] = mapped_column(Text, nullable=True)

    despesa = relationship("Despesa", back_populates="solicitacao")
    solicitante = relationship("Usuario", foreign_keys=[solicitada_por])
    decisor = relationship("Usuario", foreign_keys=[decidida_por])
    eventos = relationship(
        "EventoSolicitacao",
        back_populates="solicitacao",
        order_by="EventoSolicitacao.id",
        passive_deletes="all",
    )

    def __repr__(self) -> str:
        return f"<SolicitacaoAprovacao {self.id} despesa={self.despesa_id} {self.status}>"


class EventoSolicitacao(db.Model):
    """Um passo do histórico de um pedido. Somente inserção."""

    __tablename__ = "evento_solicitacao"
    __table_args__ = (CheckConstraint(f"tipo IN {SQL_TIPOS_EVENTO}", name="tipo_valido"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    solicitacao_id: Mapped[int] = mapped_column(
        ForeignKey("solicitacao_aprovacao.id"), nullable=False, index=True
    )
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    # Vazio quando o evento é do sistema (rejeição automática).
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora_utc
    )

    solicitacao = relationship("SolicitacaoAprovacao", back_populates="eventos")
    usuario = relationship("Usuario")

    def __repr__(self) -> str:
        return f"<EventoSolicitacao {self.id} {self.tipo}>"


@event.listens_for(Session, "before_flush")
def _impedir_alteracao_de_evento(session, _flush_context, _instances):
    for obj in session.deleted:
        if isinstance(obj, EventoSolicitacao):
            raise EventoImutavelError("Eventos de pedido não podem ser removidos.")
    for obj in session.dirty:
        if isinstance(obj, EventoSolicitacao) and session.is_modified(
            obj, include_collections=False
        ):
            raise EventoImutavelError("Eventos de pedido não podem ser alterados.")


@event.listens_for(Session, "do_orm_execute")
def _impedir_update_delete_de_evento_em_lote(estado):
    if not (estado.is_update or estado.is_delete):
        return
    mapper = estado.bind_mapper
    tabela = getattr(estado.statement, "table", None)
    if (mapper is not None and mapper.class_ is EventoSolicitacao) or (
        tabela is not None and getattr(tabela, "name", None) == EventoSolicitacao.__tablename__
    ):
        raise EventoImutavelError("Eventos de pedido são somente inserção.")
