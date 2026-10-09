"""Decisão sobre os pedidos: aprovar, rejeitar, encaminhar e regras de permissão."""

import pytest


@pytest.fixture
def pendente(auditor, historico, lancar):
    return lancar(auditor, "140.00").solicitacao


@pytest.fixture
def automatica(auditor, historico, lancar):
    return lancar(auditor, "2500.00").solicitacao


def test_aprovar(sessao, pendente, administrador):
    from app.servicos import solicitacoes

    solicitacoes.aprovar(pendente, administrador, "Viagem autorizada.")
    sessao.commit()

    assert pendente.status == "aprovada"
    assert pendente.despesa.situacao == "valida"
    assert (pendente.decidida_por, pendente.justificativa) == (
        administrador.id,
        "Viagem autorizada.",
    )
    assert [e.tipo for e in pendente.eventos] == ["criada", "aprovada"]
    for alerta in pendente.despesa.alertas:
        assert alerta.status_revisao == "aprovado"
        assert f"pedido #{pendente.id}" in alerta.pareceres[-1].observacao


def test_rejeitar_exige_justificativa(sessao, pendente, administrador):
    from app.servicos import solicitacoes

    with pytest.raises(solicitacoes.SolicitacaoInvalidaError, match="justificativa"):
        solicitacoes.rejeitar(pendente, administrador, "  ")

    solicitacoes.rejeitar(pendente, administrador, "Sem autorização.")
    sessao.commit()

    assert (pendente.status, pendente.despesa.situacao) == ("rejeitada", "rejeitada")
    assert all(a.status_revisao == "irregular" for a in pendente.despesa.alertas)


def test_so_administrador_decide(pendente, auditor):
    from app.servicos import solicitacoes

    with pytest.raises(solicitacoes.SolicitacaoInvalidaError, match="administrador"):
        solicitacoes.aprovar(pendente, auditor)


def test_quem_lancou_nao_decide_o_proprio_pedido(
    historico, lancar, administrador, outro_administrador
):
    from app.servicos import solicitacoes

    pedido = lancar(administrador, "140.00").solicitacao

    assert not solicitacoes.pode_decidir(pedido, administrador)
    with pytest.raises(solicitacoes.SolicitacaoInvalidaError, match="próprio pedido"):
        solicitacoes.aprovar(pedido, administrador)
    solicitacoes.aprovar(pedido, outro_administrador)
    assert pedido.status == "aprovada"


def test_pedido_ja_decidido(sessao, pendente, administrador):
    from app.servicos import solicitacoes

    solicitacoes.aprovar(pendente, administrador)
    with pytest.raises(solicitacoes.SolicitacaoInvalidaError, match="não está pendente"):
        solicitacoes.rejeitar(pendente, administrador, "x")


def test_encaminhar_rejeitado_automaticamente(sessao, automatica, auditor, administrador):
    from app.servicos import solicitacoes

    assert solicitacoes.pode_encaminhar(automatica, auditor)
    with pytest.raises(solicitacoes.SolicitacaoInvalidaError, match="reavaliada"):
        solicitacoes.encaminhar(automatica, auditor, "")

    solicitacoes.encaminhar(automatica, auditor, "Compra emergencial autorizada pela diretoria.")
    sessao.commit()
    assert (automatica.status, automatica.prioritaria) == ("pendente", True)
    assert automatica.despesa.situacao == "rejeitada"  # continua inválida até a decisão
    assert [e.tipo for e in automatica.eventos][-1] == "encaminhada"

    solicitacoes.aprovar(automatica, administrador)
    assert automatica.despesa.situacao == "valida"


def test_encaminhar_so_rejeitados_automaticamente(pendente, auditor):
    from app.servicos import solicitacoes

    with pytest.raises(solicitacoes.SolicitacaoInvalidaError, match="automaticamente"):
        solicitacoes.encaminhar(pendente, auditor, "x")


def test_outro_auditor_nao_encaminha(sessao, automatica):
    from app.servicos import solicitacoes
    from tests.conftest import _criar_usuario

    outro = _criar_usuario(sessao, "outro@teste.com", "auditor")
    assert not solicitacoes.pode_encaminhar(automatica, outro)
    with pytest.raises(solicitacoes.SolicitacaoInvalidaError, match="quem lançou"):
        solicitacoes.encaminhar(automatica, outro, "x")


def test_ordem_da_fila(sessao, auditor, historico, lancar):
    from app.servicos import solicitacoes

    comum = lancar(auditor, "140.00").solicitacao
    rejeitada = lancar(auditor, "2500.00", funcionario="F010").solicitacao
    solicitacoes.encaminhar(rejeitada, auditor, "Reavaliar, por favor.")
    sessao.commit()

    ids = [s.id for s in solicitacoes.paginar().items]
    assert ids.index(rejeitada.id) < ids.index(comum.id)  # prioritária primeiro
    assert solicitacoes.contar_por_status()["prioritarios"] == 1


def test_historico_do_pedido_e_somente_insercao(sessao, pendente):
    from app.models import EventoImutavelError

    evento = pendente.eventos[0]
    evento.observacao = "alterado"
    with pytest.raises(EventoImutavelError):
        sessao.flush()
    sessao.rollback()
