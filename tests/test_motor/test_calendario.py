"""Calendário de feriados nacionais e dias úteis."""

from datetime import date

import pytest

from motor.calendario import dias_no_intervalo, eh_dia_util, eh_feriado, feriados_do_ano, pascoa


@pytest.mark.parametrize(
    ("ano", "esperada"),
    [
        (2000, date(2000, 4, 23)),
        (2019, date(2019, 4, 21)),
        (2024, date(2024, 3, 31)),
        (2025, date(2025, 4, 20)),
        (2026, date(2026, 4, 5)),
        (2027, date(2027, 3, 28)),
    ],
)
def test_pascoa(ano, esperada):
    assert pascoa(ano) == esperada


def test_feriados_moveis_de_2026():
    feriados = feriados_do_ano(2026)
    assert {date(2026, 2, 16), date(2026, 2, 17)} <= feriados  # Carnaval
    assert date(2026, 4, 3) in feriados  # Sexta-feira Santa
    assert date(2026, 6, 4) in feriados  # Corpus Christi


def test_feriados_fixos():
    feriados = feriados_do_ano(2025)
    assert date(2025, 11, 20) in feriados  # Consciência Negra
    assert date(2025, 12, 25) in feriados
    assert len(feriados) == 13  # 9 fixos + 4 móveis


def test_dia_util_exclui_fim_de_semana_e_feriado():
    assert eh_dia_util(date(2026, 9, 23))  # quarta-feira
    assert not eh_dia_util(date(2026, 9, 26))  # sábado
    assert not eh_dia_util(date(2026, 9, 7))  # segunda, Independência
    assert eh_feriado(date(2026, 9, 7))


def test_dias_no_intervalo_inclui_as_pontas():
    dias = dias_no_intervalo(date(2026, 1, 30), date(2026, 2, 2))
    assert dias == [date(2026, 1, 30), date(2026, 1, 31), date(2026, 2, 1), date(2026, 2, 2)]
