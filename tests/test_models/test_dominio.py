"""Valores de domínio (não dependem de banco)."""

from app.models import dominio


def test_perfis_sao_apenas_auditor_e_administrador():
    assert dominio.PERFIS == ("auditor", "administrador")


def test_parecer_nao_aceita_status_pendente():
    assert dominio.STATUS_PENDENTE not in dominio.STATUS_PARECER
    assert set(dominio.STATUS_PARECER) < set(dominio.STATUS_REVISAO)


def test_status_que_exigem_observacao():
    assert set(dominio.STATUS_EXIGEM_OBSERVACAO) == {"irregular", "necessita_justificativa"}


def test_parametros_padrao_cobrem_os_quatro_metodos():
    assert set(dominio.PARAMETROS_PADRAO) == set(dominio.METODOS)
    assert dominio.PARAMETROS_PADRAO["zscore"]["limiar"] == "3"
    assert dominio.PARAMETROS_PADRAO["iqr"]["fator"] == "1.5"
    assert dominio.PARAMETROS_PADRAO["isolation_forest"] == {
        "contamination": "0.05",
        "random_state": "42",
        "limite_aprovacao": "1000",
    }
    assert dominio.PARAMETROS_PADRAO["contextual"]["frequencia_minima"] == "0.01"


def test_lista_sql_das_check_constraints():
    assert dominio.SQL_PERFIS == "('auditor', 'administrador')"
