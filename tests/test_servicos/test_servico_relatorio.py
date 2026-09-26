"""Relatório mensal (US11)."""

from datetime import date
from decimal import Decimal

import pytest


@pytest.fixture
def cenario(sessao, auditor):
    """Março/2026: 4 despesas (R$ 1.000), 3 sinalizadas, 5 alertas.

    Alertas de março: irregular, irregular, aprovado, pendente, necessita_justificativa.
    Abril e fevereiro têm despesas e alertas que não podem entrar no relatório.
    """
    from app.models import AlertaAnomalia, Despesa, ExecucaoAnalise

    execucao = ExecucaoAnalise(parametros={}, seed=42, executada_por=auditor.id)

    def despesa(dia, valor):
        return Despesa(
            valor=Decimal(valor),
            data=dia,
            categoria="Viagens",
            conta_contabil="3.1",
            centro_custo="CC-ADM",
            funcionario="F001",
        )

    def alerta(d, metodo, status):
        return AlertaAnomalia(
            despesa=d,
            execucao=execucao,
            metodo=metodo,
            score=1.0,
            motivo="m",
            status_revisao=status,
        )

    inicio, meio, fim, sem_alerta = (
        despesa(date(2026, 3, 1), "400.00"),  # primeiro dia do mês
        despesa(date(2026, 3, 15), "300.00"),
        despesa(date(2026, 3, 31), "200.00"),  # último dia do mês
        despesa(date(2026, 3, 20), "100.00"),
    )
    fevereiro, abril = despesa(date(2026, 2, 28), "999.00"), despesa(date(2026, 4, 1), "999.00")
    alertas = [
        alerta(inicio, "zscore", "irregular"),
        alerta(inicio, "iqr", "irregular"),
        alerta(meio, "contextual", "aprovado"),
        alerta(fim, "isolation_forest", "pendente"),
        alerta(fim, "zscore", "necessita_justificativa"),
        alerta(fevereiro, "zscore", "aprovado"),
        alerta(abril, "zscore", "irregular"),
    ]
    sessao.add_all([execucao, inicio, meio, fim, sem_alerta, fevereiro, abril, *alertas])
    sessao.commit()
    return execucao


def test_indicadores_do_mes(cenario):
    from app.servicos.relatorio import relatorio_mensal

    r = relatorio_mensal(2026, 3)

    assert (r["inicio"], r["fim"]) == (date(2026, 3, 1), date(2026, 3, 31))
    assert (r["total_despesas"], r["valor_despesas"]) == (4, Decimal("1000.00"))
    assert (r["despesas_sinalizadas"], r["valor_sinalizado"]) == (3, Decimal("900.00"))
    assert r["percentual_sinalizado"] == 75.0
    assert r["total_alertas"] == 5
    assert r["alertas_por_status"] == {
        "pendente": 1,
        "aprovado": 1,
        "irregular": 2,
        "necessita_justificativa": 1,
    }
    assert r["alertas_por_metodo"] == {
        "zscore": 2,
        "iqr": 1,
        "isolation_forest": 1,
        "contextual": 1,
    }
    # irregular ÷ (aprovado + irregular) = 2 ÷ 3
    assert r["alertas_concluidos"] == 3
    assert r["taxa_confirmacao"] == pytest.approx(66.67)
    assert r["alertas_irregulares"] == 2
    assert r["taxa_confirmacao_texto"] == "66,67% (2 de 3)"
    assert r["ultima_analise"].id == cenario.id


def test_taxa_indefinida_sem_alertas_concluidos(sessao, auditor, alerta):
    from app.servicos.relatorio import relatorio_mensal

    r = relatorio_mensal(2026, 9)  # o alerta da fixture está pendente

    assert r["total_alertas"] == 1
    assert r["taxa_confirmacao"] is None
    assert r["taxa_confirmacao_texto"] == "indefinida (nenhum alerta com conclusão)"


def test_mes_sem_despesas(sessao):
    from app.servicos.relatorio import relatorio_mensal

    r = relatorio_mensal("2026", "1")

    assert (r["total_despesas"], r["percentual_sinalizado"], r["taxa_confirmacao"]) == (
        0,
        0.0,
        None,
    )
    assert r["nome_mes"] == "janeiro"


@pytest.mark.parametrize(
    ("ano", "mes"), [(None, 3), (2026, None), ("x", 3), (1999, 3), (2026, 13), (2026, 0)]
)
def test_periodo_invalido(sessao, ano, mes):
    from app.servicos.relatorio import PeriodoInvalidoError, relatorio_mensal

    with pytest.raises(PeriodoInvalidoError):
        relatorio_mensal(ano, mes)


def test_csv(cenario):
    from app.servicos.relatorio import para_csv, relatorio_mensal

    linhas = para_csv(relatorio_mensal(2026, 3)).splitlines()

    assert linhas[0] == "secao;item;valor"
    assert "resumo;valor_despesas;1000,00" in linhas
    assert "resumo;taxa_confirmacao_percentual;66,67" in linhas
    assert "resumo;alertas_irregulares;2" in linhas
    assert "alertas_por_status;irregular;2" in linhas
    assert "alertas_por_metodo;contextual;1" in linhas


def test_mes_mais_recente(cenario):
    from app.servicos.relatorio import mes_mais_recente

    assert mes_mais_recente() == (2026, 4)


def _texto_do_pdf(conteudo: bytes) -> str:
    """Junta os textos (operador Tj) de um PDF não comprimido, desfazendo os escapes."""
    import re

    trechos = re.findall(rb"\(((?:\\.|[^\\)])*)\) Tj", conteudo)
    return " ".join(
        re.sub(
            rb"\\([0-7]{3}|.)", lambda m: bytes([int(m[1], 8)]) if len(m[1]) == 3 else m[1], t
        ).decode("latin-1")
        for t in trechos
    )


def test_pdf(cenario):
    from app.servicos.relatorio import para_pdf, relatorio_mensal

    conteudo = para_pdf(relatorio_mensal(2026, 3), comprimir=False)
    texto = _texto_do_pdf(conteudo)

    assert conteudo.startswith(b"%PDF-")
    assert "Relatório mensal de anomalias em despesas" in texto
    assert "Março de 2026 (despesas de 01/03/2026 a 31/03/2026)" in texto
    assert "indícios estatísticos, não acusações" in texto  # RNF04 também no PDF
    assert "4 (R$ 1.000,00)" in texto
    assert "66,67% (2 de 3)" in texto
    assert "Necessita justificativa" in texto and "Isolation Forest" in texto
    assert f"Última análise: nº {cenario.id}" in texto


def test_pdf_sem_analise_e_taxa_indefinida(sessao):
    from app.servicos.relatorio import para_pdf, relatorio_mensal

    texto = _texto_do_pdf(para_pdf(relatorio_mensal(2026, 1), comprimir=False))

    assert "indefinida (nenhum alerta com conclusão)" in texto
    assert "Nenhuma análise foi executada ainda" in texto


def test_pdf_comprimido_e_menor(cenario):
    from app.servicos.relatorio import para_pdf, relatorio_mensal

    relatorio = relatorio_mensal(2026, 3)
    assert len(para_pdf(relatorio)) < len(para_pdf(relatorio, comprimir=False))
