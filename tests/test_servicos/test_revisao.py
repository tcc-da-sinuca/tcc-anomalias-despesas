"""Serviço de revisão: classificação e parecer (US07, US08, RF12, RNF02)."""

import pytest


def test_registra_parecer_e_atualiza_o_status(sessao, alerta, auditor):
    from app.servicos.revisao import registrar_parecer

    parecer = registrar_parecer(alerta, auditor, "aprovado", None)
    sessao.commit()

    assert parecer.id is not None
    assert (parecer.alerta_id, parecer.usuario_id, parecer.status) == (
        alerta.id,
        auditor.id,
        "aprovado",
    )
    assert parecer.observacao is None
    assert parecer.criado_em is not None
    assert alerta.status_revisao == "aprovado"


@pytest.mark.parametrize("status", ["irregular", "necessita_justificativa"])
@pytest.mark.parametrize("observacao", [None, "", "   "])
def test_observacao_obrigatoria(sessao, alerta, auditor, status, observacao):
    from app.models import Parecer
    from app.servicos.revisao import ParecerInvalidoError, registrar_parecer

    with pytest.raises(ParecerInvalidoError, match="observação é obrigatória") as erro:
        registrar_parecer(alerta, auditor, status, observacao)

    assert erro.value.campo == "observacao"
    assert sessao.query(Parecer).count() == 0
    assert alerta.status_revisao == "pendente"


@pytest.mark.parametrize("status", [None, "", "pendente", "qualquer"])
def test_status_invalido(sessao, alerta, auditor, status):
    from app.servicos.revisao import ParecerInvalidoError, registrar_parecer

    with pytest.raises(ParecerInvalidoError) as erro:
        registrar_parecer(alerta, auditor, status, "texto")
    assert erro.value.campo == "status"


def test_observacao_sem_espacos_nas_pontas(sessao, alerta, auditor):
    from app.servicos.revisao import registrar_parecer

    parecer = registrar_parecer(alerta, auditor, "irregular", "  Nota fiscal ausente.  ")
    assert parecer.observacao == "Nota fiscal ausente."


def test_novo_parecer_mantem_o_historico(sessao, alerta, auditor, administrador):
    from app.servicos.revisao import registrar_parecer

    registrar_parecer(alerta, auditor, "necessita_justificativa", "Pedir o recibo.")
    sessao.commit()
    registrar_parecer(alerta, administrador, "aprovado", "Recibo apresentado.")
    sessao.commit()
    sessao.refresh(alerta)

    assert [p.status for p in alerta.pareceres] == ["necessita_justificativa", "aprovado"]
    assert [p.usuario_id for p in alerta.pareceres] == [auditor.id, administrador.id]
    assert alerta.status_revisao == "aprovado"
