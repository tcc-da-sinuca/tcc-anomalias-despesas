"""Job de reprocessamento das despesas novas."""

from datetime import date
from decimal import Decimal

import pytest


def _despesas(sessao, quantidade, valor="100.00"):
    from app.models import Despesa

    sessao.add_all(
        Despesa(
            valor=Decimal(valor),
            data=date(2026, 3, 2),
            categoria="Viagens",
            conta_contabil="3.1.01",
            centro_custo="CC-ADM",
            funcionario="F001",
        )
        for _ in range(quantidade)
    )
    sessao.commit()


def test_sem_despesas_nao_roda(sessao):
    from app.servicos.reprocessamento import reprocessar

    assert reprocessar() is None


def test_roda_so_quando_ha_despesas_novas(sessao):
    from app.servicos.reprocessamento import reprocessar

    _despesas(sessao, 20)
    primeira = reprocessar()
    sessao.commit()
    assert primeira is not None
    assert primeira.executada_por is None  # execução automática, sem autor
    assert primeira.total_despesas == 20

    assert reprocessar() is None  # nada mudou

    _despesas(sessao, 1, valor="5000.00")
    segunda = reprocessar()
    sessao.commit()
    assert segunda is not None and segunda.total_despesas == 21


def test_analise_manual_completa_conta_como_ultima(sessao, auditor):
    from app.servicos.analise import executar_analise
    from app.servicos.reprocessamento import reprocessar

    _despesas(sessao, 20)
    executar_analise(auditor)
    sessao.commit()

    assert reprocessar() is None


def test_analise_parcial_nao_conta(sessao, auditor):
    from app.servicos.analise import executar_analise
    from app.servicos.reprocessamento import reprocessar, ultima_analise_completa

    _despesas(sessao, 20)
    executar_analise(auditor, ["zscore"])
    sessao.commit()

    assert ultima_analise_completa() is None
    assert reprocessar() is not None


@pytest.fixture
def cli(app):
    return app.test_cli_runner()


def test_comando_uma_vez(cli, sessao, caplog):
    _despesas(sessao, 20)

    resultado = cli.invoke(args=["agendador", "--uma-vez"])

    assert resultado.exit_code == 0, resultado.output
    from app.models import ExecucaoAnalise

    assert sessao.query(ExecucaoAnalise).count() == 1


def test_comando_desativado(app, cli):
    app.config["REPROCESSAMENTO_INTERVALO_MIN"] = 0
    resultado = cli.invoke(args=["agendador"])

    assert resultado.exit_code == 0
    assert "Reprocessamento desativado" in resultado.output


def test_comando_agenda_o_job(app, cli, monkeypatch):
    from apscheduler.schedulers.blocking import BlockingScheduler

    agendados = []
    monkeypatch.setattr(BlockingScheduler, "start", lambda self: agendados.extend(self.get_jobs()))
    app.config["REPROCESSAMENTO_INTERVALO_MIN"] = 7

    resultado = cli.invoke(args=["agendador"])

    assert resultado.exit_code == 0, resultado.output
    assert [job.id for job in agendados] == ["reprocessamento"]
    assert agendados[0].trigger.interval.total_seconds() == 7 * 60


def test_falha_no_job_e_registrada_e_nao_derruba(cli, monkeypatch, caplog):
    import app.servicos.reprocessamento as modulo

    def falhar():
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(modulo, "reprocessar", falhar)
    resultado = cli.invoke(args=["agendador", "--uma-vez"])

    assert resultado.exit_code == 0
    assert "Falha no reprocessamento" in caplog.text
