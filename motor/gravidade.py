"""Gravidade de um alerta: quanto o score passou do limite do próprio método.

Cada detector devolve, além do score, o ``excesso``: o score dividido pelo limite do
método (1,0 = exatamente no limite; 3,0 = três vezes o limite). Os métodos têm escalas
muito diferentes (o Isolation Forest passa do limite no máximo ~1,3 vez; o IQR chega a
~27), por isso cada um tem as suas faixas.

As faixas vêm dos quantis 50%, 80% e 95% do excesso das despesas sinalizadas na base
sintética (seed 42), arredondados, **sem usar os rótulos de anomalia**: metade dos
alertas de cada método é "leve", os 5% mais extremos são "crítica".

Só o Z-score e o IQR chegam a "crítica". A escala deles tem significado estável
(desvios padrão e amplitudes interquartis) e, no experimento, todo alerta crítico era
anomalia (seeds 42 e 7). Os outros dois vão no máximo até "alta":

- regra contextual: combinação incomum de conta e centro de custo costuma ser erro de
  classificação, não motivo para rejeitar a despesa sozinho;
- Isolation Forest: o score depende do tamanho e da forma de cada base (num histórico
  pequeno, qualquer desvio passa de 1,3x o limite), e os "críticos" dele acertaram só
  ~50% no experimento, porque ele marca também a original de cada duplicata.

Despesa com algum alerta "crítica" é rejeitada automaticamente no lançamento
(``NIVEL_REJEICAO_AUTOMATICA``; decisão da equipe, item 33 de MUDANCAS_PARA_DOCUMENTACAO.md).
"""

LEVE, MODERADA, ALTA, CRITICA = "leve", "moderada", "alta", "critica"
NIVEIS = (LEVE, MODERADA, ALTA, CRITICA)
NOMES_NIVEIS = {LEVE: "Leve", MODERADA: "Moderada", ALTA: "Alta", CRITICA: "Crítica"}
NIVEL_REJEICAO_AUTOMATICA = CRITICA

# metodo → excesso mínimo para (moderada, alta, critica); None = o nível não existe.
FAIXAS = {
    "zscore": (1.5, 2.0, 3.5),
    "iqr": (1.75, 3.5, 9.0),
    "isolation_forest": (1.19, 1.24, None),
    "contextual": (2.0, 4.0, None),
}


def classificar(metodo: str, excesso: float | None) -> str | None:
    """Nível de gravidade de um alerta. ``None`` se o excesso não for conhecido."""
    if excesso is None or excesso != excesso:  # NaN
        return None
    nivel = LEVE
    for limite, proximo in zip(FAIXAS[metodo], (MODERADA, ALTA, CRITICA), strict=True):
        if limite is not None and excesso >= limite:
            nivel = proximo
    return nivel


def mais_grave(niveis) -> str | None:
    """O nível mais grave de uma lista (ignora ``None``)."""
    presentes = [n for n in niveis if n in NIVEIS]
    return max(presentes, key=NIVEIS.index) if presentes else None
