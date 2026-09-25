"""Leitura dos parâmetros dos métodos para o motor."""

import pytest

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


def test_regras_cobrem_os_parametros_padrao_e_aceitam_os_padroes():
    from app.servicos.parametros import REGRAS, validar

    assert {r.nome for r in REGRAS} == {
        f"{metodo}.{chave}" for metodo, itens in PARAMETROS_PADRAO.items() for chave in itens
    }
    for regra in REGRAS:
        validar(regra, PARAMETROS_PADRAO[regra.metodo][regra.chave])  # não levanta


@pytest.mark.parametrize(
    ("nome", "bruto", "esperado"),
    [
        ("zscore.limiar", "2,5", 2.5),
        ("zscore.limiar", 10, 10.0),
        ("isolation_forest.random_state", "7", 7),
        ("isolation_forest.contamination", 0.5, 0.5),
    ],
)
def test_validar_aceita(nome, bruto, esperado):
    from app.servicos.parametros import REGRAS_POR_NOME, validar

    assert validar(REGRAS_POR_NOME[nome], bruto) == esperado


@pytest.mark.parametrize(
    ("nome", "bruto", "trecho"),
    [
        ("zscore.limiar", "0.5", "de 1 a 10"),
        ("zscore.limiar", "abc", "informe um número"),
        ("zscore.limiar", "", "informe um número"),
        ("zscore.limiar", "inf", "informe um número"),
        ("isolation_forest.contamination", "0", "maior que 0 e até 0,5"),
        ("isolation_forest.contamination", "0.51", "maior que 0 e até 0,5"),
        ("isolation_forest.random_state", "4.5", "número inteiro"),
        ("isolation_forest.random_state", "-1", "de 0 a"),
        ("isolation_forest.limite_aprovacao", "0", "maior que 0"),
    ],
)
def test_validar_recusa(nome, bruto, trecho):
    from app.servicos.parametros import REGRAS_POR_NOME, validar

    with pytest.raises(ValueError, match=trecho):
        validar(REGRAS_POR_NOME[nome], bruto)


def test_atualizar_grava_valor_autor_e_data(sessao, administrador):
    from app.models import ParametroMetodo
    from app.servicos.parametros import atualizar_parametros, garantir_parametros_padrao

    garantir_parametros_padrao()
    sessao.commit()

    alterados = atualizar_parametros(
        {"zscore": {"limiar": "2,5"}, "iqr": {"fator": 1.5}}, administrador
    )
    sessao.commit()

    assert alterados == ["zscore.limiar"]  # o fator do IQR não mudou
    parametro = sessao.get(ParametroMetodo, ("zscore", "limiar"))
    assert parametro.valor == "2.5"
    assert parametro.alterado_por == administrador.id
    assert sessao.get(ParametroMetodo, ("iqr", "fator")).alterado_por is None


def test_atualizar_e_tudo_ou_nada(sessao, administrador):
    from app.models import ParametroMetodo
    from app.servicos.parametros import (
        ParametrosInvalidosError,
        atualizar_parametros,
        garantir_parametros_padrao,
    )

    garantir_parametros_padrao()
    sessao.commit()

    with pytest.raises(ParametrosInvalidosError) as erro:
        atualizar_parametros(
            {"zscore": {"limiar": 2}, "iqr": {"fator": 99}, "xyz": {"a": 1}}, administrador
        )

    assert set(erro.value.erros) == {"iqr.fator", "xyz.a"}
    sessao.rollback()
    assert sessao.get(ParametroMetodo, ("zscore", "limiar")).valor == "3"


def test_listar_parametros(sessao, administrador):
    from app.servicos.parametros import atualizar_parametros, listar_parametros

    atualizar_parametros({"isolation_forest": {"limite_aprovacao": 500}}, administrador)
    sessao.commit()
    itens = {item["regra"].nome: item for item in listar_parametros()}

    assert itens["zscore.limiar"]["valor"] == 3.0 and itens["zscore.limiar"]["alterado_por"] is None
    limite = itens["isolation_forest.limite_aprovacao"]
    assert (limite["valor"], limite["padrao"]) == (500.0, 1000.0)
    assert limite["alterado_por"].id == administrador.id


def test_salvar_o_padrao_sem_linha_gravada_nao_conta_como_alteracao(sessao, administrador):
    from app.servicos.parametros import atualizar_parametros

    # sem garantir_parametros_padrao(): nenhuma linha em ParametroMetodo
    assert atualizar_parametros({"zscore": {"limiar": 3}, "iqr": {"fator": 2}}, administrador) == [
        "iqr.fator"
    ]
