"""Construção de DataFrames de despesas para os testes do motor (sem fixtures)."""

import pandas as pd


def montar_despesas(linhas: list[dict]) -> pd.DataFrame:
    """Completa cada linha com os campos do contrato e numera ``despesa_id`` a partir de 1."""
    padrao = {
        "data": pd.Timestamp("2026-03-02"),
        "categoria": "Viagens",
        "conta_contabil": "3.1.01",
        "centro_custo": "CC-ADM",
        "funcionario": "F001",
    }
    df = pd.DataFrame([{**padrao, **linha} for linha in linhas])
    df.insert(0, "despesa_id", range(1, len(df) + 1))
    return df


def grupo_com_extremo(n_normais=20, extremo=1000.0, categoria="Viagens"):
    """``n_normais`` valores entre 95 e 105 e, por último, um valor extremo."""
    valores = [95.0 + (i % 11) for i in range(n_normais)] + [extremo]
    return [{"valor": v, "categoria": categoria} for v in valores]
