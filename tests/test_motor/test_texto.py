"""Formatação dos números nos motivos (RNF05)."""

from motor import texto


def test_numero():
    assert texto.numero(4.23) == "4,2"
    assert texto.numero(3.0) == "3"
    assert texto.numero(1234.5) == "1.234,5"
    assert texto.numero(-3.25, 2) == "-3,25"
    assert texto.numero(1451, 0) == "1.451"


def test_moeda_e_percentual():
    assert texto.moeda(1234.5) == "R$ 1.234,50"
    assert texto.moeda(0.1) == "R$ 0,10"
    assert texto.percentual(0.0037) == "0,37%"
    assert texto.percentual(0.01) == "1%"


def test_grupo():
    assert texto.grupo("categoria", "Viagens") == "da categoria Viagens"
    assert texto.grupo("centro_custo", "CC-TI") == "do centro de custo CC-TI"
