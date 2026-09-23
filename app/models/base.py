"""Utilidades comuns aos modelos."""

from datetime import UTC, datetime


def agora_utc() -> datetime:
    """Timestamp com fuso (UTC), usado como padrão das colunas de data/hora."""
    return datetime.now(UTC)
