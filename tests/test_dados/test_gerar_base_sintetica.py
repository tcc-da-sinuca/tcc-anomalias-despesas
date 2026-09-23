"""Gerador da base sintética: reprodutibilidade, formato e cada tipo de anomalia."""

import json
from decimal import Decimal

import pandas as pd
import pytest

from dados import gerar_base_sintetica as g
from motor.calendario import dias_no_intervalo, eh_dia_util

CONFIG = g.ConfiguracaoBase(n=3000)


@pytest.fixture(scope="module")
def base():
    return g.gerar_base(CONFIG)


@pytest.fixture(scope="module")
def normais(base):
    return base[base["anomalia_real"] == 0]


def _anomalias(base, tipo):
    return base[(base["anomalia_real"] == 1) & (base["tipo_anomalia"] == tipo)]


def _dias_uteis_entre(inicio, fim):
    """Quantos dias úteis há entre duas datas, sem contar a primeira."""
    inicio, fim = min(inicio, fim), max(inicio, fim)
    return sum(eh_dia_util(d) for d in dias_no_intervalo(inicio, fim)) - eh_dia_util(inicio)


def test_mesma_seed_gera_a_mesma_base(base):
    pd.testing.assert_frame_equal(base, g.gerar_base(CONFIG))


def test_seed_diferente_gera_outra_base(base):
    outra = g.gerar_base(g.ConfiguracaoBase(n=3000, seed=7))
    assert not base.equals(outra)


def test_formato(base):
    assert tuple(base.columns) == g.COLUNAS
    assert len(base) == CONFIG.n
    assert base["id_sintetico"].tolist() == list(range(1, CONFIG.n + 1))
    assert base["data"].is_monotonic_increasing
    assert base["data"].between(CONFIG.inicio, CONFIG.fim).all()


def test_campos_obrigatorios_preenchidos(base):
    for coluna in g.COLUNAS_DESPESA:
        assert (base[coluna].astype(str).str.strip() != "").all(), coluna
    assert all(isinstance(v, Decimal) and v > 0 for v in base["valor"])
    assert all(v.as_tuple().exponent == -2 for v in base["valor"])


def test_cada_funcionario_pertence_a_um_centro_de_custo(base):
    assert (base.groupby("funcionario")["centro_custo"].nunique() == 1).all()


def test_normais_so_em_dias_uteis(normais):
    assert normais["data"].map(eh_dia_util).all()


def test_quantidade_de_eventos_por_tipo(base):
    info = g.metadados(base, CONFIG)
    esperado = round(CONFIG.n * CONFIG.taxa_anomalias) // len(g.TIPOS_ANOMALIA)
    for tipo in g.TIPOS_ANOMALIA:
        assert info["anomalias_por_tipo"][tipo]["eventos"] == esperado, tipo
    assert info["linhas_anomalas"] == int(base["anomalia_real"].sum())
    assert info["linhas_normais"] + info["linhas_anomalas"] == CONFIG.n


def test_valor_extremo(base):
    for linha in _anomalias(base, g.TIPO_VALOR_EXTREMO).itertuples():
        mediana = Decimal(str(g.CATEGORIAS[linha.categoria].mediana))
        assert linha.valor >= mediana * Decimal(str(g.FATOR_EXTREMO[0]))


def test_combinacao_incompativel_nao_existe_nas_normais(base, normais):
    combinacoes_normais = set(
        zip(normais["categoria"], normais["conta_contabil"], normais["centro_custo"], strict=True)
    )
    incompativeis = _anomalias(base, g.TIPO_COMBINACAO_INCOMPATIVEL)
    for linha in incompativeis.itertuples():
        assert (linha.categoria, linha.conta_contabil, linha.centro_custo) not in (
            combinacoes_normais
        )


def test_duplicada_repete_a_original(base):
    duplicadas = base[base["tipo_anomalia"] == g.TIPO_DUPLICADA]
    campos = ["valor", "categoria", "conta_contabil", "centro_custo", "funcionario", "descricao"]
    for grupo in duplicadas["grupo_anomalia"]:
        par = base[base["grupo_anomalia"] == grupo]
        assert sorted(par["anomalia_real"]) == [0, 1]
        assert (par[campos].nunique() == 1).all()
        original, copia = par.sort_values("anomalia_real")["data"]
        assert _dias_uteis_entre(original, copia) <= g.ATRASO_DUPLICADA_DIAS[1]


def test_fracionamento_logo_abaixo_do_limite(base):
    limite = CONFIG.limite_fracionamento
    partes = _anomalias(base, g.TIPO_FRACIONAMENTO)
    assert (partes["valor"] < limite).all()
    assert (partes["valor"] >= limite * Decimal(str(g.FAIXA_FRACIONAMENTO[0]))).all()
    assert partes["categoria"].isin(g.CATEGORIAS_FRACIONAMENTO).all()
    for _, grupo in partes.groupby("grupo_anomalia"):
        assert g.PARTES_FRACIONAMENTO[0] <= len(grupo) <= g.PARTES_FRACIONAMENTO[1]
        colunas = ["categoria", "conta_contabil", "centro_custo", "funcionario"]
        assert (grupo[colunas].nunique() == 1).all()
        assert grupo["data"].map(eh_dia_util).all()
        dias = _dias_uteis_entre(grupo["data"].min(), grupo["data"].max())
        assert dias < g.JANELA_FRACIONAMENTO_DIAS


def test_fim_semana_feriado(base):
    linhas = _anomalias(base, g.TIPO_FIM_SEMANA_FERIADO)
    assert len(linhas) > 0
    assert not linhas["data"].map(eh_dia_util).any()


@pytest.mark.parametrize(
    "alteracao",
    [{"n": 100}, {"taxa_anomalias": 0}, {"taxa_anomalias": 0.5}, {"limite_fracionamento": 0}],
)
def test_configuracao_invalida(alteracao):
    with pytest.raises(ValueError):
        g.gerar_base(g.ConfiguracaoBase(**alteracao))


def test_salvar_base(tmp_path):
    config = g.ConfiguracaoBase(n=300)
    base = g.gerar_base(config)
    caminhos = g.salvar_base(base, config, tmp_path)

    lida = pd.read_csv(caminhos["csv"], dtype=str, keep_default_na=False)
    assert tuple(lida.columns) == g.COLUNAS
    assert lida["valor"].tolist() == [str(v) for v in base["valor"]]

    assert len(pd.read_excel(caminhos["xlsx"])) == 300

    info = json.loads(caminhos["metadados"].read_text(encoding="utf-8"))
    assert info["seed"] == 42
    assert info["total_linhas"] == 300
    assert info["parametros"]["limite_fracionamento"] == "1000.00"


def test_main_grava_os_arquivos(tmp_path, capsys):
    g.main(["--n", "300", "--seed", "3", "--saida", str(tmp_path)])
    assert (tmp_path / "despesas_sinteticas.csv").exists()
    assert "seed 3" in capsys.readouterr().out
