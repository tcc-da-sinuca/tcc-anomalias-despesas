"""Lançamento com verificação na hora: válida, pedido pendente ou rejeição automática."""

from sqlalchemy import func, select


def test_dentro_do_padrao_entra_como_valida(sessao, auditor, historico, lancar):
    from app.models import ExecucaoAnalise

    resultado = lancar(auditor, "101.00")

    assert resultado.situacao == "valida"
    assert resultado.solicitacao is None and resultado.alertas == []
    assert sessao.scalar(select(func.count(ExecucaoAnalise.id))) == 0  # nada a registrar


def test_fora_do_padrao_abre_pedido_pendente(sessao, auditor, historico, lancar):
    from app.models import ExecucaoAnalise

    resultado = lancar(auditor, "140.00")
    solicitacao = resultado.solicitacao

    assert resultado.situacao == "pendente"
    assert (solicitacao.status, solicitacao.gravidade, solicitacao.prioritaria) == (
        "pendente",
        "alta",
        False,
    )
    assert solicitacao.solicitada_por == auditor.id
    assert [e.tipo for e in solicitacao.eventos] == ["criada"]
    alertas = resultado.despesa.alertas
    assert {a.metodo for a in alertas} >= {"zscore", "iqr"}
    assert all(a.gravidade and a.status_revisao == "pendente" for a in alertas)
    execucao = sessao.get(ExecucaoAnalise, alertas[0].execucao_id)
    assert execucao.parametros["tipo"] == "verificacao_lancamento"
    assert execucao.executada_por == auditor.id


def test_gravidade_critica_rejeita_automaticamente(sessao, auditor, historico, lancar):
    resultado = lancar(auditor, "2500.00")
    solicitacao = resultado.solicitacao

    assert resultado.situacao == "rejeitada"
    assert (solicitacao.status, solicitacao.gravidade) == ("rejeitada_automaticamente", "critica")
    eventos = solicitacao.eventos
    assert [e.tipo for e in eventos] == ["criada", "rejeitada_automaticamente"]
    assert eventos[1].usuario_id is None  # decisão do sistema
    assert "iqr" in eventos[1].observacao and "zscore" in eventos[1].observacao


def test_so_despesas_validas_sao_historico(sessao, auditor, historico, lancar):
    from app.models import EstatisticaReferencia
    from app.servicos.analise import carregar_despesas, executar_analise

    lancar(auditor, "140.00")
    lancar(auditor, "2500.00")

    assert len(carregar_despesas()) == 120
    viagens = sessao.scalar(
        select(EstatisticaReferencia).where(
            EstatisticaReferencia.dimensao == "categoria", EstatisticaReferencia.chave == "Viagens"
        )
    )
    assert viagens is None or viagens.n == 120
    assert executar_analise(auditor).total_despesas == 120


def test_reprocessamento_ignora_as_verificacoes(sessao, auditor, historico, lancar):
    from app.servicos.analise import executar_analise
    from app.servicos.reprocessamento import reprocessar, ultima_analise_completa

    completa = executar_analise(None)
    sessao.commit()
    lancar(auditor, "140.00")  # cria uma execução de verificação, mais recente

    assert ultima_analise_completa().id == completa.id
    assert reprocessar() is None  # o total de despesas válidas não mudou


def test_importacao_verifica_linha_a_linha(sessao, auditor, historico):
    from app.models import Despesa
    from app.servicos.importacao import importar_arquivo

    csv = (
        b"valor,data,categoria,conta_contabil,centro_custo,funcionario\n"
        b"101.00,2026-03-10,Viagens,3.1.01,CC-ADM,F005\n"
        b"140.00,2026-03-11,Viagens,3.1.01,CC-ADM,F006\n"
        b"2500.00,2026-03-12,Viagens,3.1.01,CC-ADM,F007\n"
    )
    lote = importar_arquivo("novas.csv", csv, auditor)
    sessao.commit()

    situacoes = sorted(
        sessao.scalars(select(Despesa.situacao).where(Despesa.lote_id == lote.id)).all()
    )
    assert situacoes == ["pendente", "rejeitada", "valida"]
    assert lote.linhas_validas == 3


def test_carga_do_historico_nao_verifica(sessao, auditor, historico):
    from app.models import SolicitacaoAprovacao
    from app.servicos.importacao import importar_arquivo

    csv = (
        b"valor,data,categoria,conta_contabil,centro_custo,funcionario\n"
        b"2500.00,2026-03-12,Viagens,3.1.01,CC-ADM,F007\n"
    )
    importar_arquivo("historico.csv", csv, auditor, verificar=False)
    sessao.commit()

    assert sessao.scalar(select(func.count(SolicitacaoAprovacao.id))) == 0


def test_pendentes_e_rejeitadas_ficam_fora_dos_indicadores(sessao, auditor, historico, lancar):
    from app.repositorios.alertas import paginar_alertas
    from app.servicos.dashboard import resumo
    from app.servicos.relatorio import relatorio_mensal

    lancar(auditor, "140.00")
    lancar(auditor, "2500.00")

    assert resumo()["total_despesas"] == 120
    assert resumo()["total_alertas"] == 0
    assert paginar_alertas().total == 0
    assert relatorio_mensal(2026, 3)["total_despesas"] == 120


def test_ultima_analise_do_dashboard_ignora_verificacoes(sessao, auditor, historico, lancar):
    from app.servicos.analise import executar_analise
    from app.servicos.dashboard import resumo

    analise = executar_analise(auditor)
    sessao.commit()
    lancar(auditor, "140.00")

    assert resumo()["ultima_analise"].id == analise.id
