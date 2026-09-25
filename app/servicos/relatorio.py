"""Relatório mensal (RF11 / US11).

O mês de referência é o da **data da despesa** (o mesmo critério do filtro de
período). Indicadores:

- total analisado: despesas com data no mês (quantidade e valor);
- anomalias: despesas do mês sinalizadas (distintas) e alertas por método e status;
- taxa de confirmação de irregularidade = irregular ÷ (aprovado + irregular), pelo
  status atual dos alertas das despesas do mês (item 18 de
  MUDANCAS_PARA_DOCUMENTACAO.md). Fica indefinida (``None``) sem alertas concluídos.

Informa também a última análise, porque o sistema não registra quais despesas
entraram em cada análise: uma despesa importada depois dela ainda não foi analisada.
"""

import calendar
import csv
import io
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.extensoes import db
from app.models import AlertaAnomalia, Despesa, ExecucaoAnalise
from app.models.dominio import (
    METODOS,
    STATUS_APROVADO,
    STATUS_IRREGULAR,
    STATUS_REVISAO,
)

ANO_MINIMO, ANO_MAXIMO = 2000, 2100
NOMES_MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)  # fmt: skip


class PeriodoInvalidoError(ValueError):
    """Ano ou mês ausente ou fora da faixa."""


def validar_periodo(ano, mes) -> tuple[int, int]:
    """Converte e valida ``ano`` e ``mes`` (texto ou número)."""
    try:
        ano, mes = int(ano), int(mes)
    except (TypeError, ValueError):
        raise PeriodoInvalidoError("Informe o ano e o mês como números.") from None
    if not ANO_MINIMO <= ano <= ANO_MAXIMO:
        raise PeriodoInvalidoError(f"O ano deve estar entre {ANO_MINIMO} e {ANO_MAXIMO}.")
    if not 1 <= mes <= 12:
        raise PeriodoInvalidoError("O mês deve estar entre 1 e 12.")
    return ano, mes


def mes_mais_recente() -> tuple[int, int]:
    """Mês da despesa mais recente (ou o mês atual, se não houver despesas)."""
    ultima = db.session.scalar(select(func.max(Despesa.data)))
    referencia = ultima or date.today()
    return referencia.year, referencia.month


def relatorio_mensal(ano, mes) -> dict:
    """Indicadores do mês. Levanta ``PeriodoInvalidoError``."""
    ano, mes = validar_periodo(ano, mes)
    inicio = date(ano, mes, 1)
    fim = date(ano, mes, calendar.monthrange(ano, mes)[1])
    no_mes = (Despesa.data >= inicio, Despesa.data <= fim)

    total_despesas, valor_despesas = db.session.execute(
        select(func.count(Despesa.id), func.coalesce(func.sum(Despesa.valor), 0)).where(*no_mes)
    ).one()

    sinalizadas = select(AlertaAnomalia.despesa_id).distinct().scalar_subquery()
    despesas_sinalizadas, valor_sinalizado = db.session.execute(
        select(func.count(Despesa.id), func.coalesce(func.sum(Despesa.valor), 0)).where(
            *no_mes, Despesa.id.in_(sinalizadas)
        )
    ).one()

    def contar_alertas(coluna, chaves):
        contagem = dict.fromkeys(chaves, 0)
        contagem.update(
            db.session.execute(
                select(coluna, func.count(AlertaAnomalia.id))
                .join(AlertaAnomalia.despesa)
                .where(*no_mes)
                .group_by(coluna)
            ).all()
        )
        return contagem

    por_status = contar_alertas(AlertaAnomalia.status_revisao, STATUS_REVISAO)
    por_metodo = contar_alertas(AlertaAnomalia.metodo, METODOS)
    concluidos = por_status[STATUS_APROVADO] + por_status[STATUS_IRREGULAR]
    taxa = round(100 * por_status[STATUS_IRREGULAR] / concluidos, 2) if concluidos else None

    ultima = db.session.scalar(
        select(ExecucaoAnalise).order_by(
            ExecucaoAnalise.iniciada_em.desc(), ExecucaoAnalise.id.desc()
        )
    )
    return {
        "ano": ano,
        "mes": mes,
        "nome_mes": NOMES_MESES[mes - 1],
        "inicio": inicio,
        "fim": fim,
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
        "alertas_concluidos": concluidos,
        "taxa_confirmacao": taxa,
        "ultima_analise": ultima,
    }


def _numero_br(valor) -> str:
    """Número para o CSV no padrão do Excel brasileiro: 1234.5 → "1234,5"."""
    return str(valor).replace(".", ",")


def para_csv(relatorio: dict) -> str:
    """CSV (separador ``;``, vírgula decimal) em formato longo: seção; item; valor."""
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\n")
    escritor.writerow(["secao", "item", "valor"])
    ultima = relatorio["ultima_analise"]
    linhas = [
        ("periodo", "ano", relatorio["ano"]),
        ("periodo", "mes", relatorio["mes"]),
        ("periodo", "inicio", relatorio["inicio"].isoformat()),
        ("periodo", "fim", relatorio["fim"].isoformat()),
        ("resumo", "total_despesas", relatorio["total_despesas"]),
        ("resumo", "valor_despesas", _numero_br(relatorio["valor_despesas"])),
        ("resumo", "despesas_sinalizadas", relatorio["despesas_sinalizadas"]),
        ("resumo", "valor_sinalizado", _numero_br(relatorio["valor_sinalizado"])),
        ("resumo", "percentual_sinalizado", _numero_br(relatorio["percentual_sinalizado"])),
        ("resumo", "total_alertas", relatorio["total_alertas"]),
        ("resumo", "alertas_concluidos", relatorio["alertas_concluidos"]),
        (
            "resumo",
            "taxa_confirmacao_percentual",
            ""
            if relatorio["taxa_confirmacao"] is None
            else _numero_br(relatorio["taxa_confirmacao"]),
        ),
        *(("alertas_por_status", s, n) for s, n in relatorio["alertas_por_status"].items()),
        *(("alertas_por_metodo", m, n) for m, n in relatorio["alertas_por_metodo"].items()),
        ("analise", "ultima_analise_id", ultima.id if ultima else ""),
        ("analise", "ultima_analise_em", ultima.iniciada_em.isoformat() if ultima else ""),
    ]
    escritor.writerows(linhas)
    return saida.getvalue()
