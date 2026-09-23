"""Calendário de feriados nacionais e dias úteis.

Usado pelo gerador da base sintética (lançamentos em fim de semana ou feriado)
e, na Sprint 3, pelos atributos derivados do Isolation Forest.

Além dos feriados nacionais oficiais, a lista inclui Carnaval (segunda e terça)
e Corpus Christi. Eles são pontos facultativos na esfera federal, mas a maioria
das empresas não trabalha nesses dias.
"""

from datetime import date, timedelta

# (mês, dia) dos feriados nacionais de data fixa.
FERIADOS_FIXOS = (
    (1, 1),  # Confraternização Universal
    (4, 21),  # Tiradentes
    (5, 1),  # Dia do Trabalho
    (9, 7),  # Independência
    (10, 12),  # Nossa Senhora Aparecida
    (11, 2),  # Finados
    (11, 15),  # Proclamação da República
    (11, 20),  # Dia Nacional de Zumbi e da Consciência Negra (Lei 14.759/2023)
    (12, 25),  # Natal
)


def pascoa(ano: int) -> date:
    """Domingo de Páscoa no calendário gregoriano (algoritmo de Meeus/Jones/Butcher)."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    j = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * j) // 451
    mes, dia = divmod(h + j - 7 * m + 114, 31)
    return date(ano, mes, dia + 1)


def feriados_do_ano(ano: int) -> set[date]:
    """Feriados nacionais do ano, com os móveis (Carnaval, Sexta-feira Santa, Corpus Christi)."""
    domingo_pascoa = pascoa(ano)
    moveis = {
        domingo_pascoa - timedelta(days=48),  # segunda de Carnaval
        domingo_pascoa - timedelta(days=47),  # terça de Carnaval
        domingo_pascoa - timedelta(days=2),  # Sexta-feira Santa
        domingo_pascoa + timedelta(days=60),  # Corpus Christi
    }
    return {date(ano, mes, dia) for mes, dia in FERIADOS_FIXOS} | moveis


def eh_feriado(dia: date) -> bool:
    return dia in feriados_do_ano(dia.year)


def eh_dia_util(dia: date) -> bool:
    """Segunda a sexta, exceto feriados."""
    return dia.weekday() < 5 and not eh_feriado(dia)


def dias_no_intervalo(inicio: date, fim: date) -> list[date]:
    """Todos os dias de ``inicio`` a ``fim``, inclusive."""
    return [inicio + timedelta(days=i) for i in range((fim - inicio).days + 1)]
