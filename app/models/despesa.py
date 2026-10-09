"""Lotes de importação e despesas corporativas (RF01)."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensoes import db
from app.models.base import agora_utc
from app.models.dominio import SITUACAO_VALIDA, SQL_SITUACOES_DESPESA


class LoteImportacao(db.Model):
    """Um arquivo CSV/XLSX importado. Guarda os erros por linha (US01)."""

    __tablename__ = "lote_importacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome_arquivo: Mapped[str] = mapped_column(String(255), nullable=False)
    importado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    importado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=agora_utc
    )
    total_linhas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    linhas_validas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Lista de erros: [{"linha": 7, "campo": "valor", "mensagem": "..."}]
    erros: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    usuario = relationship("Usuario")
    despesas = relationship("Despesa", back_populates="lote")

    def __repr__(self) -> str:
        return f"<LoteImportacao {self.id} {self.nome_arquivo}>"


class Despesa(db.Model):
    """Lançamento de despesa corporativa.

    Campos obrigatórios (US01): valor, data, categoria, conta contábil,
    centro de custo e funcionário. ``lote_id`` fica vazio no cadastro manual.

    ``situacao``: ``valida`` (dentro do padrão ou aprovada), ``pendente`` (fora do padrão,
    aguardando a decisão de um pedido de aprovação) ou ``rejeitada``. Só as válidas
    contam como histórico, análise, dashboard e relatório.
    """

    __tablename__ = "despesa"
    __table_args__ = (
        CheckConstraint(f"situacao IN {SQL_SITUACOES_DESPESA}", name="situacao_valida"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    data: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    categoria: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    conta_contabil: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    centro_custo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    funcionario: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    lote_id: Mapped[int | None] = mapped_column(
        ForeignKey("lote_importacao.id"), nullable=True, index=True
    )
    situacao: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=SITUACAO_VALIDA,
        server_default=SITUACAO_VALIDA,
        index=True,
    )

    lote = relationship("LoteImportacao", back_populates="despesas")
    alertas = relationship("AlertaAnomalia", back_populates="despesa")
    solicitacao = relationship("SolicitacaoAprovacao", back_populates="despesa", uselist=False)

    def __repr__(self) -> str:
        return f"<Despesa {self.id} {self.categoria} R$ {self.valor}>"
