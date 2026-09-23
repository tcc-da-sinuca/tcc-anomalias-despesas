"""Pareceres de revisão (RF06–RF08) e parâmetros dos métodos (RF13).

O ``Parecer`` é somente inserção (RNF02). A imutabilidade é garantida em duas
camadas:

1. na aplicação, pelos eventos do SQLAlchemy definidos neste módulo, que
   rejeitam alteração ou remoção de um parecer, inclusive por update/delete em
   lote;
2. no banco, por um trigger do PostgreSQL criado na migration inicial, que
   bloqueia UPDATE, DELETE e TRUNCATE mesmo fora da aplicação.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, event
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.extensoes import db
from app.models.base import agora_utc
from app.models.dominio import SQL_METODOS, SQL_STATUS_EXIGEM_OBSERVACAO, SQL_STATUS_PARECER


class ParecerImutavelError(Exception):
    """Tentativa de alterar ou remover um parecer já registrado."""


class Parecer(db.Model):
    """Decisão do auditor sobre um alerta. Somente inserção.

    Uma revisão nova gera um novo parecer. O histórico completo continua
    disponível (RF12).
    """

    __tablename__ = "parecer"
    __table_args__ = (
        CheckConstraint(f"status IN {SQL_STATUS_PARECER}", name="status_valido"),
        # RF08/US08: observação obrigatória para "irregular" e "necessita_justificativa".
        CheckConstraint(
            f"status NOT IN {SQL_STATUS_EXIGEM_OBSERVACAO} "
            "OR (observacao IS NOT NULL AND length(trim(observacao)) > 0)",
            name="observacao_obrigatoria",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alerta_id: Mapped[int] = mapped_column(
        ForeignKey("alerta_anomalia.id"), nullable=False, index=True
    )
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    observacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora_utc
    )

    alerta = relationship("AlertaAnomalia", back_populates="pareceres")
    usuario = relationship("Usuario")

    def __repr__(self) -> str:
        return f"<Parecer {self.id} alerta={self.alerta_id} {self.status}>"


class ParametroMetodo(db.Model):
    """Parâmetro configurável de um método de detecção (RF13 / US12).

    A chave primária é o par (metodo, chave), por exemplo ("zscore", "limiar").
    O valor fica como texto; a conversão e a validação são feitas pelo serviço
    de parâmetros.
    """

    __tablename__ = "parametro_metodo"
    __table_args__ = (CheckConstraint(f"metodo IN {SQL_METODOS}", name="metodo_valido"),)

    metodo: Mapped[str] = mapped_column(String(20), primary_key=True)
    chave: Mapped[str] = mapped_column(String(50), primary_key=True)
    valor: Mapped[str] = mapped_column(String(100), nullable=False)
    alterado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    alterado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora_utc
    )

    usuario = relationship("Usuario")

    def __repr__(self) -> str:
        return f"<ParametroMetodo {self.metodo}.{self.chave}={self.valor}>"


# --- Imutabilidade do parecer na camada de aplicação --------------------------


@event.listens_for(Session, "before_flush")
def _impedir_alteracao_de_parecer(session, _flush_context, _instances):
    for obj in session.deleted:
        if isinstance(obj, Parecer):
            raise ParecerImutavelError("Pareceres não podem ser removidos (RNF02).")
    for obj in session.dirty:
        if isinstance(obj, Parecer) and session.is_modified(obj, include_collections=False):
            raise ParecerImutavelError(
                "Pareceres não podem ser alterados (RNF02). Registre um novo parecer."
            )


@event.listens_for(Session, "do_orm_execute")
def _impedir_update_delete_em_lote(estado):
    if not (estado.is_update or estado.is_delete):
        return
    mapper = estado.bind_mapper
    tabela = getattr(estado.statement, "table", None)
    alvo_e_parecer = (mapper is not None and mapper.class_ is Parecer) or (
        tabela is not None and getattr(tabela, "name", None) == Parecer.__tablename__
    )
    if alvo_e_parecer:
        raise ParecerImutavelError(
            "Pareceres são somente inserção (RNF02): UPDATE/DELETE não permitido."
        )
