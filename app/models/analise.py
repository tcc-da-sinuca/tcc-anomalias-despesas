"""Estatísticas de referência, execuções de análise e alertas (RF02–RF05, RF12)."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensoes import db
from app.models.base import agora_utc
from app.models.dominio import SQL_METODOS, SQL_STATUS_REVISAO, STATUS_PENDENTE


class EstatisticaReferencia(db.Model):
    """Estatísticas de um grupo de despesas (US02).

    ``dimensao`` indica o agrupamento (ex.: "categoria", ou uma combinação como
    "categoria|centro_custo") e ``chave`` o valor do grupo (ex.: "Viagens" ou
    "Viagens|CC-01"). Há no máximo um registro por (dimensao, chave): o
    recálculo após nova importação substitui os valores.
    """

    __tablename__ = "estatistica_referencia"
    __table_args__ = (UniqueConstraint("dimensao", "chave"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dimensao: Mapped[str] = mapped_column(String(100), nullable=False)
    chave: Mapped[str] = mapped_column(String(255), nullable=False)
    media: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    # Desvio padrão amostral: indefinido quando n = 1, por isso pode ser nulo.
    desvio: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    q1: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    q3: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    n: Mapped[int] = mapped_column(Integer, nullable=False)
    calculada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora_utc
    )

    def __repr__(self) -> str:
        return f"<EstatisticaReferencia {self.dimensao}={self.chave} n={self.n}>"


class ExecucaoAnalise(db.Model):
    """Uma execução do motor de detecção (RF12, RNF06).

    ``parametros`` guarda uma cópia dos parâmetros usados e ``seed`` a semente,
    para que a execução possa ser reproduzida. ``executada_por`` fica vazio
    quando a execução é disparada por um job agendado.
    """

    __tablename__ = "execucao_analise"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    iniciada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora_utc
    )
    duracao_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    parametros: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    total_despesas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_alertas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    executada_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)

    usuario = relationship("Usuario")
    alertas = relationship("AlertaAnomalia", back_populates="execucao")

    def __repr__(self) -> str:
        return f"<ExecucaoAnalise {self.id} alertas={self.total_alertas}>"


class AlertaAnomalia(db.Model):
    """Indício de anomalia gerado por um método para uma despesa (RF04).

    Um alerta é um indício estatístico, não uma acusação: sempre exige revisão
    humana. ``status_revisao`` reflete o último parecer registrado.
    """

    __tablename__ = "alerta_anomalia"
    __table_args__ = (
        CheckConstraint(f"metodo IN {SQL_METODOS}", name="metodo_valido"),
        CheckConstraint(f"status_revisao IN {SQL_STATUS_REVISAO}", name="status_revisao_valido"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    despesa_id: Mapped[int] = mapped_column(ForeignKey("despesa.id"), nullable=False, index=True)
    execucao_id: Mapped[int] = mapped_column(
        ForeignKey("execucao_analise.id"), nullable=False, index=True
    )
    metodo: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    status_revisao: Mapped[str] = mapped_column(
        String(30), nullable=False, default=STATUS_PENDENTE, index=True
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora_utc
    )

    despesa = relationship("Despesa", back_populates="alertas")
    execucao = relationship("ExecucaoAnalise", back_populates="alertas")
    # passive_deletes="all": o ORM nunca altera pareceres ao remover um alerta;
    # a FK do banco impede a remoção de alertas que já têm parecer.
    pareceres = relationship(
        "Parecer",
        back_populates="alerta",
        order_by="Parecer.criado_em",
        passive_deletes="all",
    )

    def __repr__(self) -> str:
        return f"<AlertaAnomalia {self.id} {self.metodo} score={self.score:.3f}>"
