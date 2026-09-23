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


def registrar_filtros(app: Flask) -> None:
    app.add_template_filter(moeda)
    app.add_template_filter(data_br)
    app.add_template_filter(data_hora_br)
