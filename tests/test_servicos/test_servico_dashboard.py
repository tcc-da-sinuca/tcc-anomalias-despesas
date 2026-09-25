"""Indicadores do dashboard (US09)."""

from datetime import date
from decimal import Decimal

import pytest


@pytest.fixture
def cenario(sessao, auditor):
    """4 despesas; a 1ª tem dois alertas (zscore e iqr), a 2ª um alerta; 3ª e 4ª sem alertas."""
    from app.models import AlertaAnomalia, Despesa, ExecucaoAnalise

    despesas = [
        Despesa(
            valor=Decimal(valor),
            data=date(2026, 3, 2),
            categoria="Viagens",
            conta_contabil="3.1",
            centro_custo="CC-ADM",
            funcionario="F001",
        )
        for valor in ("1000.00", "250.50", "100.00", "49.50")
    ]
    execucao = ExecucaoAnalise(parametros={}, seed=42, executada_por=auditor.id)
    alertas = [
        AlertaAnomalia(
            despesa=despesas[0], execucao=execucao, metodo="zscore", score=5.0, motivo="m"
        ),
        AlertaAnomalia(
            despesa=despesas[0],
            execucao=execucao,
            metodo="iqr",
            score=3.0,
            motivo="m",
            status_revisao="irregular",
        ),
        AlertaAnomalia(
            despesa=despesas[1],
            execucao=execucao,
            metodo="contextual",
            score=0.99,
            motivo="m",
            status_revisao="aprovado",
        ),
    ]
    sessao.add_all([*despesas, execucao, *alertas])
    sessao.commit()
    return execucao


def test_indicadores(cenario):
    from app.servicos.dashboard import resumo

    r = resumo()

    assert (r["total_despesas"], r["valor_despesas"]) == (4, Decimal("1400.00"))
    # despesa com dois alertas conta uma vez
    assert (r["despesas_sinalizadas"], r["valor_sinalizado"]) == (2, Decimal("1250.50"))
    assert r["percentual_sinalizado"] == 50.0
    assert r["total_alertas"] == 3
    assert r["alertas_por_status"] == {
        "pendente": 1,
        "aprovado": 1,
        "irregular": 1,
        "necessita_justificativa": 0,
    }
    assert r["alertas_por_metodo"] == {
        "zscore": 1,
        "iqr": 1,
        "isolation_forest": 0,
        "contextual": 1,
    }
    assert r["ultima_analise"].id == cenario.id


def test_sem_dados(sessao):
    from app.servicos.dashboard import resumo

    r = resumo()

    assert (r["total_despesas"], r["despesas_sinalizadas"], r["total_alertas"]) == (0, 0, 0)
    assert r["percentual_sinalizado"] == 0.0
    assert r["valor_despesas"] == Decimal("0")
    assert r["ultima_analise"] is None
