"""Serviço de estatísticas de referência (US02)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.servicos.estatisticas import listar_estatisticas, recalcular_estatisticas


def _despesa(valor, categoria="Viagens", conta="3.1", centro="CC-01"):
    from app.models import Despesa

    return Despesa(
        valor=Decimal(valor),
        data=date(2026, 9, 1),
        categoria=categoria,
        conta_contabil=conta,
        centro_custo=centro,
        funcionario="F001",
    )


def _estatistica(sessao, dimensao, chave):
    from app.models import EstatisticaReferencia

    return sessao.scalar(
        select(EstatisticaReferencia).where(
            EstatisticaReferencia.dimensao == dimensao, EstatisticaReferencia.chave == chave
        )
    )


def test_grava_as_estatisticas_por_dimensao(sessao):
    sessao.add_all([_despesa("10"), _despesa("20"), _despesa("30"), _despesa("40")])
    sessao.add(_despesa("100", categoria="Software", conta="3.5", centro="CC-TI"))
    sessao.flush()

    grupos = recalcular_estatisticas()
    sessao.commit()

    assert grupos == 6  # 2 categorias + 2 contas + 2 centros de custo
    viagens = _estatistica(sessao, "categoria", "Viagens")
    assert viagens.n == 4
    assert viagens.media == Decimal("25.0000")
    assert viagens.desvio == Decimal("12.9099")
    assert (viagens.q1, viagens.q3) == (Decimal("17.5000"), Decimal("32.5000"))
    assert _estatistica(sessao, "categoria", "Software").desvio is None
    assert viagens.calculada_em is not None


def test_recalculo_substitui_os_valores_anteriores(sessao):
    from app.models import EstatisticaReferencia

    sessao.add_all([_despesa("10"), _despesa("30")])
    sessao.flush()
    recalcular_estatisticas()
    sessao.add(_despesa("50", categoria="Hospedagem"))
    sessao.flush()

    recalcular_estatisticas()
    sessao.commit()

    assert _estatistica(sessao, "centro_custo", "CC-01").n == 3
    chaves = set(sessao.scalars(select(EstatisticaReferencia.chave)))
    assert chaves == {"Viagens", "Hospedagem", "3.1", "CC-01"}


def test_sem_despesas_nao_grava_nada(sessao):
    assert recalcular_estatisticas() == 0


def test_listar_agrupa_por_dimensao(sessao):
    sessao.add_all([_despesa("10"), _despesa("20", categoria="Alimentação")])
    sessao.flush()
    recalcular_estatisticas()

    por_dimensao = listar_estatisticas()

    assert list(por_dimensao) == ["categoria", "conta_contabil", "centro_custo"]
    assert [e.chave for e in por_dimensao["categoria"]] == ["Alimentação", "Viagens"]
