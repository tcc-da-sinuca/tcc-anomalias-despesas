"""Leitura dos parâmetros dos métodos para o motor."""

from app.models.dominio import PARAMETROS_PADRAO


def test_padroes_quando_nada_foi_gravado(sessao):
    from app.servicos.parametros import obter_parametros

    parametros = obter_parametros()

    assert set(parametros) == set(PARAMETROS_PADRAO)
    assert parametros["zscore"] == {"limiar": 3.0}
    assert parametros["isolation_forest"] == {
        "contamination": 0.05,
        "random_state": 42,
        "limite_aprovacao": 1000.0,
    }
    assert isinstance(parametros["isolation_forest"]["random_state"], int)


def test_valores_gravados_substituem_os_padroes(sessao):
    from app.models import ParametroMetodo
    from app.servicos.parametros import garantir_parametros_padrao, obter_parametros

    garantir_parametros_padrao()
    sessao.get(ParametroMetodo, ("iqr", "fator")).valor = "3"
    sessao.commit()

    assert obter_parametros()["iqr"] == {"fator": 3.0}
