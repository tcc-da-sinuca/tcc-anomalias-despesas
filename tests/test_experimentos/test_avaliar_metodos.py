"""Script do experimento: métricas, combinações e arquivos gerados."""

import json
import math

import pandas as pd
import pytest

from experimentos import avaliar_metodos as exp


def test_metricas_calculadas_a_mao():
    real = pd.Series([1, 1, 1, 0, 0, 0, 0, 0])
    previsto = pd.Series([1, 1, 0, 1, 0, 0, 0, 0])

    m = exp.metricas(real, previsto)

    assert (m["vp"], m["fp"], m["fn"], m["vn"]) == (2, 1, 1, 4)
    assert m["precisao"] == pytest.approx(2 / 3)
    assert m["recall"] == pytest.approx(2 / 3)
    assert m["f1"] == pytest.approx(2 / 3)
    assert m["taxa_fp"] == pytest.approx(1 / 5)
    assert m["sinalizadas"] == 3


def test_metricas_indefinidas_quando_nada_e_sinalizado():
    m = exp.metricas(pd.Series([1, 0, 0]), pd.Series([0, 0, 0]))

    assert math.isnan(m["precisao"])
    assert m["recall"] == 0
    assert m["f1"] == 0
    assert m["taxa_fp"] == 0


def test_unioes_e_votacao():
    sinalizado = pd.DataFrame(
        {
            "a": [True, False, False, True],
            "b": [False, True, False, True],
            "c": [False, False, False, True],
        }
    )
    por_nome = {nome: previsto.tolist() for _, nome, _, previsto in exp.avaliacoes(sinalizado)}

    assert set(por_nome) == {"a", "b", "c", "a+b", "a+c", "b+c", "a+b+c", ">=2 de a+b+c"}
    assert por_nome["a+b"] == [True, True, False, True]
    assert por_nome[">=2 de a+b+c"] == [False, False, False, True]


def test_ler_parametros():
    parametros = exp.ler_parametros(["zscore.limiar=2.5"], ["zscore", "iqr"])

    assert parametros == {"zscore": {"limiar": 2.5}, "iqr": {"fator": 1.5}}
    with pytest.raises(SystemExit):
        exp.ler_parametros(["zscore.nao_existe=1"], ["zscore"])
    with pytest.raises(SystemExit):
        exp.ler_parametros(["sem_igual"], ["zscore"])


@pytest.fixture(scope="module")
def saida(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("resultados")
    exp.main(["--saida", str(pasta)])
    return pasta


def test_gera_os_arquivos_com_seed_e_parametros(saida):
    metricas = pd.read_csv(saida / "metricas.csv")

    assert tuple(metricas.columns) == exp.COLUNAS_METRICAS
    assert metricas["nome"].tolist()[:3] == ["zscore", "iqr", "contextual"]
    assert (metricas["seed_base"] == 42).all()
    assert json.loads(metricas.loc[0, "parametros"]) == {"zscore": {"limiar": 3.0}}
    total = metricas[["vp", "fp", "fn", "vn"]].sum(axis=1)
    assert (total == 5000).all()

    execucao = json.loads((saida / "execucao.json").read_text(encoding="utf-8"))
    assert execucao["seed_base"] == 42
    assert execucao["metadados_base"]["linhas_anomalas"] == 216
    assert set(execucao["tempo_s_por_metodo"]) == {
        "zscore",
        "iqr",
        "contextual",
        "isolation_forest",
    }


def test_recorte_por_tipo_soma_as_linhas_da_base(saida):
    por_tipo = pd.read_csv(saida / "metricas_por_tipo.csv")
    zscore = por_tipo[por_tipo["nome"] == "zscore"]

    assert zscore["linhas"].sum() == 5000
    assert "normal" in set(zscore["tipo_anomalia"])
    metricas = pd.read_csv(saida / "metricas.csv").set_index("nome")
    assert zscore["sinalizadas"].sum() == metricas.loc["zscore", "sinalizadas"]


def test_resultado_e_reproduzivel(saida, tmp_path):
    exp.main(["--saida", str(tmp_path)])

    for arquivo in ("metricas.csv", "metricas_por_tipo.csv"):
        assert (tmp_path / arquivo).read_text() == (saida / arquivo).read_text()


def test_metricas_por_gravidade(saida):
    gravidade = pd.read_csv(saida / "metricas_por_gravidade.csv")

    assert tuple(gravidade.columns) == exp.COLUNAS_POR_GRAVIDADE
    assert set(gravidade["metodo"]) >= {"zscore", "iqr", "contextual", "isolation_forest"}
    por_metodo = gravidade[gravidade["metodo"] == "zscore"].set_index("gravidade")
    metricas = pd.read_csv(saida / "metricas.csv").set_index("nome")
    assert por_metodo["sinalizadas"].sum() == metricas.loc["zscore", "sinalizadas"]

    rejeicao = gravidade.set_index("metodo")
    no_lancamento = rejeicao.loc[exp.REJEICAO_NO_LANCAMENTO]
    em_lote = rejeicao.loc[exp.REJEICAO_AUTOMATICA]
    assert no_lancamento["sinalizadas"] <= em_lote["sinalizadas"]
    assert no_lancamento["anomalas"] == em_lote["anomalas"]  # só saem as originais (normais)
