"""Testes dos modelos SQLAlchemy (SQLite em memória)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from app.models import (
    AlertaAnomalia,
    Despesa,
    EstatisticaReferencia,
    ParametroMetodo,
    Parecer,
    ParecerImutavelError,
    Usuario,
)

# --- Usuário ----------------------------------------------------------------


def test_senha_armazenada_somente_como_hash(auditor):
    assert auditor.senha_hash != "senha-segura-123"
    assert auditor.verificar_senha("senha-segura-123")
    assert not auditor.verificar_senha("senha-errada")


def test_perfil_gestor_nao_existe(sessao):
    usuario = Usuario(nome="Gestor", email="gestor@teste.com", perfil="gestor")
    usuario.definir_senha("qualquer-senha")
    sessao.add(usuario)
    with pytest.raises(IntegrityError):
        sessao.commit()
    sessao.rollback()


def test_email_unico(sessao, auditor):
    repetido = Usuario(nome="Outro", email=auditor.email, perfil="auditor")
    repetido.definir_senha("qualquer-senha")
    sessao.add(repetido)
    with pytest.raises(IntegrityError):
        sessao.commit()
    sessao.rollback()


def test_usuario_inativo_nao_esta_ativo_para_o_login(usuario_inativo):
    assert usuario_inativo.is_active is False


# --- Despesa ----------------------------------------------------------------


def test_valor_da_despesa_e_decimal(sessao, alerta):
    despesa = sessao.get(Despesa, alerta.despesa_id)
    assert isinstance(despesa.valor, Decimal)
    assert despesa.valor == Decimal("1520.75")


def test_despesa_exige_campos_obrigatorios(sessao):
    # Falta o funcionário (obrigatório desde a decisão registrada em docs/).
    sessao.add(
        Despesa(
            valor=Decimal("10.00"),
            data=date(2026, 9, 1),
            categoria="Alimentação",
            conta_contabil="3.1.02",
            centro_custo="CC-02",
        )
    )
    with pytest.raises(IntegrityError):
        sessao.commit()
    sessao.rollback()


def test_despesa_cadastrada_manualmente_nao_tem_lote(sessao):
    despesa = Despesa(
        valor=Decimal("89.90"),
        data=date(2026, 9, 2),
        categoria="Material de escritório",
        conta_contabil="3.1.03",
        centro_custo="CC-03",
        funcionario="F010",
    )
    sessao.add(despesa)
    sessao.commit()
    assert despesa.lote_id is None


# --- Estatística de referência ---------------------------------------------


def test_estatistica_unica_por_dimensao_e_chave(sessao):
    def nova():
        return EstatisticaReferencia(
            dimensao="categoria",
            chave="Viagens",
            media=Decimal("1000"),
            desvio=Decimal("200"),
            q1=Decimal("850"),
            q3=Decimal("1150"),
            n=30,
        )

    sessao.add(nova())
    sessao.commit()
    sessao.add(nova())
    with pytest.raises(IntegrityError):
        sessao.commit()
    sessao.rollback()


# --- Alerta -----------------------------------------------------------------


def test_alerta_nasce_pendente_e_ligado_a_despesa_e_execucao(alerta):
    assert alerta.status_revisao == "pendente"
    assert alerta.despesa.categoria == "Viagens"
    assert alerta.execucao.seed == 42
    assert alerta in alerta.despesa.alertas


def test_alerta_rejeita_metodo_desconhecido(sessao, alerta):
    sessao.add(
        AlertaAnomalia(
            despesa_id=alerta.despesa_id,
            execucao_id=alerta.execucao_id,
            metodo="rede_neural",
            score=1.0,
            motivo="teste",
        )
    )
    with pytest.raises(IntegrityError):
        sessao.commit()
    sessao.rollback()


# --- Parecer (RF08, RNF02) --------------------------------------------------


def test_parecer_aprovado_dispensa_observacao(sessao, alerta, auditor):
    sessao.add(Parecer(alerta_id=alerta.id, usuario_id=auditor.id, status="aprovado"))
    sessao.commit()
    assert len(alerta.pareceres) == 1


@pytest.mark.parametrize("status", ["irregular", "necessita_justificativa"])
@pytest.mark.parametrize("observacao", [None, "", "   "])
def test_parecer_exige_observacao(sessao, alerta, auditor, status, observacao):
    sessao.add(
        Parecer(alerta_id=alerta.id, usuario_id=auditor.id, status=status, observacao=observacao)
    )
    with pytest.raises(IntegrityError):
        sessao.commit()
    sessao.rollback()


def test_parecer_nao_aceita_status_pendente(sessao, alerta, auditor):
    sessao.add(Parecer(alerta_id=alerta.id, usuario_id=auditor.id, status="pendente"))
    with pytest.raises(IntegrityError):
        sessao.commit()
    sessao.rollback()


@pytest.fixture
def parecer(sessao, alerta, auditor):
    parecer = Parecer(
        alerta_id=alerta.id,
        usuario_id=auditor.id,
        status="irregular",
        observacao="Nota fiscal não corresponde ao valor lançado.",
    )
    sessao.add(parecer)
    sessao.commit()
    return parecer


def test_parecer_registra_usuario_e_timestamp(parecer, auditor):
    assert parecer.usuario_id == auditor.id
    assert parecer.criado_em is not None


def test_parecer_nao_pode_ser_alterado(sessao, parecer):
    parecer.observacao = "Texto trocado depois"
    with pytest.raises(ParecerImutavelError):
        sessao.commit()
    sessao.rollback()
    assert sessao.get(Parecer, parecer.id).observacao.startswith("Nota fiscal")


def test_parecer_nao_pode_ser_removido(sessao, parecer):
    sessao.delete(parecer)
    with pytest.raises(ParecerImutavelError):
        sessao.commit()
    sessao.rollback()
    assert sessao.get(Parecer, parecer.id) is not None


def test_parecer_nao_aceita_update_em_lote(sessao, parecer):
    with pytest.raises(ParecerImutavelError):
        sessao.execute(update(Parecer).values(observacao="alterado"))
    sessao.rollback()


def test_parecer_nao_aceita_delete_em_lote(sessao, parecer):
    with pytest.raises(ParecerImutavelError):
        sessao.execute(delete(Parecer))
    sessao.rollback()
    assert sessao.scalar(select(Parecer).where(Parecer.id == parecer.id)) is not None


def test_nova_revisao_gera_novo_parecer_e_preserva_historico(
    sessao, parecer, alerta, administrador
):
    sessao.add(
        Parecer(
            alerta_id=alerta.id,
            usuario_id=administrador.id,
            status="aprovado",
            observacao="Justificativa aceita após envio do comprovante.",
        )
    )
    sessao.commit()
    sessao.refresh(alerta)
    assert [p.status for p in alerta.pareceres] == ["irregular", "aprovado"]


# --- Parâmetros dos métodos -------------------------------------------------


def test_parametros_padrao_sao_inseridos_uma_unica_vez(sessao):
    from app.servicos.parametros import garantir_parametros_padrao

    assert garantir_parametros_padrao() == 6
    sessao.commit()
    assert garantir_parametros_padrao() == 0
    assert sessao.get(ParametroMetodo, ("zscore", "limiar")).valor == "3"
    assert sessao.get(ParametroMetodo, ("isolation_forest", "random_state")).valor == "42"
