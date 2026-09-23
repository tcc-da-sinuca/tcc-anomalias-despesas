"""Serviço de análise: execução do motor e gravação dos alertas (RF03–RF05, RF12)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select


@pytest.fixture
def despesas(sessao):
    """120 despesas de Viagens em torno de R$ 100, um valor extremo e uma combinação inexistente."""
    from app.models import Despesa

    def nova(valor, centro_custo="CC-ADM"):
        return Despesa(
            valor=Decimal(valor),
            data=date(2026, 3, 2),
            categoria="Viagens",
            conta_contabil="3.1.01",
            centro_custo=centro_custo,
            funcionario="F001",
        )

    lista = [nova(f"{95 + i % 11}.00") for i in range(120)]
    extrema, rara = nova("2500.00"), nova("100.00", centro_custo="CC-TI")
    sessao.add_all([*lista, extrema, rara])
    sessao.commit()
    return {"extrema": extrema, "rara": rara}


def _alertas(sessao):
    from app.models import AlertaAnomalia

    return sessao.scalars(select(AlertaAnomalia).order_by(AlertaAnomalia.id)).all()


def test_grava_execucao_e_alertas(sessao, auditor, despesas):
    from app.servicos.analise import executar_analise

    execucao = executar_analise(auditor)
    sessao.commit()

    pares = {(a.despesa_id, a.metodo) for a in _alertas(sessao)}
    assert pares == {
        (despesas["extrema"].id, "zscore"),
        (despesas["extrema"].id, "iqr"),
        (despesas["rara"].id, "contextual"),
    }
    assert (execucao.total_despesas, execucao.total_alertas) == (122, 3)
    assert execucao.executada_por == auditor.id
    assert execucao.duracao_s is not None and execucao.duracao_s >= 0
    for alerta in _alertas(sessao):
        assert alerta.execucao_id == execucao.id
        assert alerta.status_revisao == "pendente"
        assert alerta.motivo


def test_registra_parametros_e_seed(sessao, auditor, despesas):
    from app.servicos.analise import executar_analise

    execucao = executar_analise(auditor)

    assert execucao.seed == 42
    assert execucao.parametros == {
        "metodos": ["zscore", "iqr", "contextual"],
        "zscore": {"limiar": 3.0},
        "iqr": {"fator": 1.5},
        "contextual": {"frequencia_minima": 0.01},
        "dimensao_valor": "categoria",
        "n_minimo_grupo": 10,
    }


def test_usa_os_parametros_gravados(sessao, auditor, despesas):
    from app.models import ParametroMetodo
    from app.servicos.analise import executar_analise

    sessao.add(ParametroMetodo(metodo="zscore", chave="limiar", valor="100"))
    sessao.commit()

    execucao = executar_analise(auditor, metodos=["zscore"])

    assert execucao.parametros["zscore"] == {"limiar": 100.0}
    assert execucao.total_alertas == 0


def test_reexecucao_nao_duplica_alertas(sessao, auditor, despesas):
    from app.models import Despesa
    from app.servicos.analise import executar_analise

    executar_analise(auditor)
    sessao.commit()
    nova = Despesa(
        valor=Decimal("3000.00"),
        data=date(2026, 3, 3),
        categoria="Viagens",
        conta_contabil="3.1.01",
        centro_custo="CC-ADM",
        funcionario="F002",
    )
    sessao.add(nova)
    sessao.commit()

    segunda = executar_analise(None)
    sessao.commit()

    novos = [a for a in _alertas(sessao) if a.execucao_id == segunda.id]
    assert {a.despesa_id for a in novos} == {nova.id}
    assert segunda.total_alertas == len(novos)
    assert segunda.executada_por is None  # job agendado
    assert len(_alertas(sessao)) == 3 + len(novos)


def test_so_os_metodos_pedidos(sessao, auditor, despesas):
    from app.servicos.analise import executar_analise

    execucao = executar_analise(auditor, metodos=["contextual"])

    assert {a.metodo for a in _alertas(sessao)} == {"contextual"}
    assert execucao.parametros["metodos"] == ["contextual"]
    assert "zscore" not in execucao.parametros


def test_metodo_desconhecido(sessao, auditor, despesas):
    from app.models import ExecucaoAnalise
    from app.servicos.analise import MetodoDesconhecidoError, executar_analise

    with pytest.raises(MetodoDesconhecidoError):
        executar_analise(auditor, metodos=["isolation_forest"])
    assert sessao.scalar(select(func.count(ExecucaoAnalise.id))) == 0


def test_sem_despesas(sessao, auditor):
    from app.servicos.analise import executar_analise

    execucao = executar_analise(auditor)

    assert (execucao.total_despesas, execucao.total_alertas) == (0, 0)
    assert _alertas(sessao) == []
