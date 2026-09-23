"""Formatação de números para os motivos dos alertas, no padrão brasileiro (RNF05).

O motor não usa os filtros do Flask, por isso tem a sua própria formatação.
"""


def numero(valor: float, casas: int = 1) -> str:
    """4.2 → "4,2"; 1234.5 → "1.234,5"; 3.0 → "3" (zeros à direita são removidos)."""
    texto = f"{valor:,.{casas}f}"
    if casas > 0:
        texto = texto.rstrip("0").rstrip(".")
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def moeda(valor: float) -> str:
    """1234.5 → "R$ 1.234,50"."""
    texto = f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"


def percentual(fracao: float) -> str:
    """0.0037 → "0,37%"."""
    return f"{numero(fracao * 100, 2)}%"


# "da categoria Viagens", "do centro de custo CC-TI"
NOMES_GRUPOS = {
    "categoria": "da categoria",
    "conta_contabil": "da conta contábil",
    "centro_custo": "do centro de custo",
}


def grupo(dimensao: str, chave) -> str:
    return f"{NOMES_GRUPOS.get(dimensao, 'do grupo ' + dimensao)} {chave}"
