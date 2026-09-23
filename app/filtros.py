"""Filtros Jinja para exibir valores no formato brasileiro (RNF05)."""

from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask

try:
    FUSO_EXIBICAO = ZoneInfo("America/Sao_Paulo")
except ZoneInfoNotFoundError:  # imagem sem base de fusos: exibe em UTC
    FUSO_EXIBICAO = UTC


def moeda(valor) -> str:
    """1234.5 → "R$ 1.234,50"."""
    if valor is None:
        return "—"
    quantia = Decimal(str(valor)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    texto = f"{quantia:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"


def data_br(valor: date | None) -> str:
    return valor.strftime("%d/%m/%Y") if valor else "—"


def data_hora_br(valor: datetime | None) -> str:
    if valor is None:
        return "—"
    if valor.tzinfo is None:  # SQLite devolve sem fuso; o valor gravado é UTC
        valor = valor.replace(tzinfo=UTC)
    return valor.astimezone(FUSO_EXIBICAO).strftime("%d/%m/%Y %H:%M")


NOMES_METODOS = {
    "zscore": "Z-score",
    "iqr": "IQR",
    "isolation_forest": "Isolation Forest",
    "contextual": "Contextual",
}
NOMES_STATUS = {
    "pendente": "Pendente",
    "aprovado": "Aprovado",
    "irregular": "Irregular",
    "necessita_justificativa": "Necessita justificativa",
}


def nome_metodo(metodo: str) -> str:
    return NOMES_METODOS.get(metodo, metodo)


def nome_status(status: str) -> str:
    return NOMES_STATUS.get(status, status)


def score(valor: float | None) -> str:
    """4.2371 → "4,24"."""
    return "—" if valor is None else f"{valor:.2f}".replace(".", ",")


def registrar_filtros(app: Flask) -> None:
    app.add_template_filter(moeda)
    app.add_template_filter(data_br)
    app.add_template_filter(data_hora_br)
    app.add_template_filter(nome_metodo)
    app.add_template_filter(nome_status)
    app.add_template_filter(score)
