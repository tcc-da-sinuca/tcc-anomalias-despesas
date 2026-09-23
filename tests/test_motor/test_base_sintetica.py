"""Motor aplicado à base sintética completa (seed 42).

Verificação de sanidade: cada método pega o tipo de anomalia para o qual foi
feito. Os números do artigo vêm de experimentos/avaliar_metodos.py, não daqui.
"""

import pytest

from dados.gerar_base_sintetica import gerar_base
from motor.consolidador import DETECTORES, consolidar, executar_detectores


@pytest.fixture(scope="module")
def base():
    return gerar_base().rename(columns={"id_sintetico": "despesa_id"})


@pytest.fixture(scope="module")
def resultados(base):
    return executar_detectores(base, {})


def _sinalizadas_por_tipo(base, resultado):
    tipos = base.set_index("despesa_id")["tipo_anomalia"].replace("", "normal")
    return tipos.loc[resultado.loc[resultado["sinalizado"], "despesa_id"]].value_counts()


def test_todas_as_despesas_tem_resultado(base, resultados):
    assert set(resultados) == set(DETECTORES)
    for resultado in resultados.values():
        assert len(resultado) == len(base)
        assert resultado["score"].notna().all()


def test_zscore_e_iqr_pegam_os_valores_extremos(base, resultados):
    for metodo in ("zscore", "iqr"):
        assert _sinalizadas_por_tipo(base, resultados[metodo]).get("valor_extremo", 0) >= 25


def test_contextual_pega_as_combinacoes_incompativeis(base, resultados):
    por_tipo = _sinalizadas_por_tipo(base, resultados["contextual"])
    assert por_tipo.get("combinacao_incompativel", 0) == 30


def test_alertas_tem_motivo(resultados):
    alertas = consolidar(resultados)
    assert not alertas.empty
    assert alertas["motivo"].str.len().gt(20).all()
