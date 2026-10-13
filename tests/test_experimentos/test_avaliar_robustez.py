"""Testes do experimento ampliado (experimentos/avaliar_robustez.py)."""

import pandas as pd

import dados.gerar_base_sintetica as gerador
from experimentos import avaliar_robustez as rob


def _despesas(valores):
    n = len(valores)
    return pd.DataFrame(
        {
            "despesa_id": range(1, n + 1),
            "valor": valores,
            "data": pd.to_datetime(["2026-03-02"] * n),
            "categoria": ["Viagens"] * n,
            "conta_contabil": ["3.1.01.001"] * n,
            "centro_custo": ["CC-COM"] * n,
            "funcionario": ["F001"] * n,
        }
    )


def test_zscore_robusto_sinaliza_so_o_valor_extremo():
    despesas = _despesas([100.0, 102, 98, 101, 99, 103, 97, 100, 101, 99, 5000])
    _, sinalizado = rob.zscore_robusto(despesas)
    assert sinalizado.tolist() == [False] * 10 + [True]


def test_cenario_de_estresse_restaura_as_constantes_do_gerador():
    antes = gerador.FATOR_EXTREMO
    with rob.constantes_do_gerador(FATOR_EXTREMO=(2.5, 4.0)):
        assert gerador.FATOR_EXTREMO == (2.5, 4.0)
    assert gerador.FATOR_EXTREMO == antes


def test_fim_semana_legitimo_mantem_rotulos_e_move_normais():
    base = rob.gerar(3)
    alterada = rob.com_fim_semana_legitimo(base, 3)
    assert (alterada["anomalia_real"] == base["anomalia_real"]).all()
    normais = alterada[alterada["anomalia_real"] == 0]
    assert (normais["data"].dt.dayofweek >= 5).mean() > 0.04


def test_avaliacao_reduzida_tem_os_quatro_metodos_e_as_combinacoes():
    linhas = rob.avaliar_base(rob.gerar(5), 5, completo=False)
    nomes = {linha["avaliacao"] for linha in linhas}
    assert {"zscore", "iqr", "contextual", "isolation_forest", "votacao_2"} <= nomes
