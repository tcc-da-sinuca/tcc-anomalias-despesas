"""Testes estatísticos pedidos na verificação do orientador de 06/11/2026.

Complementa ``avaliar_robustez.py`` com dois pontos:

1. **Variação da base x variação do modelo** (item 2 da verificação). Em vez de comparar
   a faixa dos 20 ``random_state`` numa única base com o desvio entre bases, roda o
   Isolation Forest num desenho cruzado: 20 bases (sementes 1 a 20) x 20 valores de
   ``random_state`` (0 a 19). Com isso, separa o desvio que vem da base do desvio que vem
   do modelo, com a mesma unidade (desvio padrão do F1 e da AP).
2. **Comparação pareada entre métodos** (item 3). Como as 20 bases são as mesmas para
   todos os métodos, cada par é comparado pela diferença por semente: média da
   diferença, intervalo de confiança de 95% (t de Student e bootstrap percentil), teste
   de postos sinalizados de Wilcoxon e correção de Holm para comparações múltiplas.

Lê ``resultados/robustez/por_semente.csv`` (gerado por ``avaliar_robustez.py``) e roda o
motor direto, sem banco nem Flask. Nenhum parâmetro da aplicação muda.

Uso::

    python -m experimentos.testes_estatisticos

Saída em ``experimentos/resultados/testes_estatisticos/``.
Regra do projeto: nenhum número vai para o artigo sem ter saído de uma execução real.
"""

import argparse
import json
import platform
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
import sklearn
from scipy import stats

from experimentos.avaliar_robustez import _do_motor, gerar, linha
from motor import isolation_forest

PASTA = Path(__file__).resolve().parent / "resultados"
ENTRADA_POR_SEMENTE = PASTA / "robustez" / "por_semente.csv"
PASTA_SAIDA = PASTA / "testes_estatisticos"
SEMENTES_BASE = range(1, 21)
RANDOM_STATES = range(20)
N_BOOTSTRAP = 10_000
SEED_BOOTSTRAP = 42
ALFA = 0.05

# Pares comparados no texto do artigo: (avaliação A, avaliação B, métrica, motivo).
PARES = [
    ("isolation_forest", "iqr", "f1", "IF é o melhor método isolado"),
    ("isolation_forest", "zscore", "f1", "IF é o melhor método isolado"),
    ("contextual+isolation_forest", "isolation_forest", "f1", "a união supera o IF sozinho"),
    ("zscore", "iqr", "f1", "ordem entre os univariados"),
    ("zscore_robusto", "zscore", "f1", "z-score robusto x clássico"),
    ("zscore_log", "zscore", "f1", "Z-score sobre log x valor bruto"),
    ("zscore_robusto_log", "zscore", "f1", "z-score robusto sobre log x clássico"),
    ("iqr_log", "iqr", "f1", "IQR sobre log x valor bruto"),
    ("zscore", "maiores_5pct_categoria", "f1", "univariado x regra trivial"),
    ("iqr", "maiores_5pct_categoria", "f1", "univariado x regra trivial"),
    ("isolation_forest", "isolation_forest_bruto", "f1", "ganho dos atributos derivados"),
    ("isolation_forest", "iqr", "ap", "AP confirma a ordem sem limiar"),
    ("isolation_forest", "zscore", "ap", "AP confirma a ordem sem limiar"),
    ("zscore_robusto", "zscore", "ap", "z-score robusto x clássico"),
]


# --- 1. Variação da base x variação do modelo ----------------------------------------


def desenho_cruzado() -> pd.DataFrame:
    linhas = []
    for seed in SEMENTES_BASE:
        base = gerar(seed)
        for rs in RANDOM_STATES:
            s, f = _do_motor(isolation_forest.detectar(base, random_state=rs), base)
            l = linha(base, "isolation_forest", "motor", s, f)
            linhas.append({"seed_base": seed, "random_state": rs,
                           **{k: l[k] for k in ("vp", "fp", "fn", "precisao", "recall", "f1", "ap")}})
    return pd.DataFrame(linhas)


def decompor(cruzado: pd.DataFrame, metrica: str) -> dict:
    """Decomposição da variância (ANOVA de um fator, base como fator aleatório)."""
    matriz = cruzado.pivot(index="seed_base", columns="random_state", values=metrica).to_numpy()
    n_bases, n_rs = matriz.shape
    var_dentro = matriz.var(axis=1, ddof=1).mean()          # modelo, com a base fixa
    var_medias = matriz.mean(axis=1).var(ddof=1)             # médias por base
    var_base = max(var_medias - var_dentro / n_rs, 0.0)      # componente da base
    total = var_base + var_dentro
    return {
        "metrica": metrica,
        "n_bases": n_bases,
        "n_random_states": n_rs,
        "media": float(matriz.mean()),
        "dp_modelo_dentro_da_base": float(np.sqrt(var_dentro)),
        "dp_base_componente": float(np.sqrt(var_base)),
        "dp_entre_bases_por_random_state_media": float(matriz.std(axis=0, ddof=1).mean()),
        "dp_total": float(matriz.std(ddof=1)),
        "fracao_variancia_base": float(var_base / total) if total else float("nan"),
        "fracao_variancia_modelo": float(var_dentro / total) if total else float("nan"),
    }


# --- 2. Comparação pareada -----------------------------------------------------------


def _ic_bootstrap(dif: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    amostras = rng.choice(dif, size=(N_BOOTSTRAP, dif.size), replace=True).mean(axis=1)
    return tuple(np.percentile(amostras, [2.5, 97.5]))


def comparar(por_semente: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(SEED_BOOTSTRAP)
    linhas = []
    for a, b, metrica, motivo in PARES:
        va = por_semente[por_semente.avaliacao == a].set_index("seed_base")[metrica]
        vb = por_semente[por_semente.avaliacao == b].set_index("seed_base")[metrica]
        comum = va.index.intersection(vb.index)
        dif = (va.loc[comum] - vb.loc[comum]).to_numpy()
        n = dif.size
        media, dp = dif.mean(), dif.std(ddof=1)
        t_crit = stats.t.ppf(1 - ALFA / 2, n - 1)
        ic_b = _ic_bootstrap(dif, rng)
        if np.allclose(dif, 0):
            p_w, estat, metodo = 1.0, float("nan"), "todas as diferenças são zero"
        else:
            # p exato quando não há zeros nem empates nas |diferenças|; senão, aproximação normal
            sem_empates = not (dif == 0).any() and np.unique(np.abs(dif)).size == n
            metodo = "exact" if sem_empates else "approx"
            w = stats.wilcoxon(va.loc[comum], vb.loc[comum], alternative="two-sided", method=metodo)
            p_w, estat = float(w.pvalue), float(w.statistic)
            metodo = "exato" if sem_empates else "aproximação normal (há empates)"
        # correlação bisserial de postos (tamanho de efeito do Wilcoxon)
        nz = dif[dif != 0]
        postos = stats.rankdata(np.abs(nz))
        efeito = (postos[nz > 0].sum() - postos[nz < 0].sum()) / postos.sum() if nz.size else 0.0
        linhas.append({
            "a": a, "b": b, "metrica": metrica, "motivo": motivo, "n_sementes": n,
            "media_a": va.loc[comum].mean(), "media_b": vb.loc[comum].mean(),
            "diferenca_media": media, "dp_diferenca": dp,
            "ic95_t_inf": media - t_crit * dp / np.sqrt(n), "ic95_t_sup": media + t_crit * dp / np.sqrt(n),
            "ic95_bootstrap_inf": ic_b[0], "ic95_bootstrap_sup": ic_b[1],
            "sementes_a_maior": int((dif > 0).sum()), "sementes_empate": int((dif == 0).sum()),
            "sementes_b_maior": int((dif < 0).sum()),
            "wilcoxon_estatistica": estat, "wilcoxon_p": p_w, "wilcoxon_metodo": metodo,
            "efeito_bisserial_postos": efeito,
        })
    tabela = pd.DataFrame(linhas)
    # Holm sobre a família inteira de comparações
    ordem = np.argsort(tabela["wilcoxon_p"].to_numpy())
    m = len(tabela)
    ajust = np.empty(m)
    acumulado = 0.0
    for posicao, i in enumerate(ordem):
        acumulado = max(acumulado, min(1.0, (m - posicao) * tabela.loc[i, "wilcoxon_p"]))
        ajust[i] = acumulado
    tabela["wilcoxon_p_holm"] = ajust
    tabela["significativo_holm_5pct"] = tabela["wilcoxon_p_holm"] < ALFA
    return tabela


def main(argv: list[str] | None = None) -> dict[str, Path]:
    parser = argparse.ArgumentParser(description="Testes estatísticos (verificação de 06/11/2026).")
    parser.add_argument("--entrada", type=Path, default=ENTRADA_POR_SEMENTE)
    parser.add_argument("--saida", type=Path, default=PASTA_SAIDA)
    args = parser.parse_args(argv)
    inicio = time.perf_counter()
    args.saida.mkdir(parents=True, exist_ok=True)
    caminhos = {}

    cruzado = desenho_cruzado()
    caminhos["cruzado"] = args.saida / "if_bases_x_random_state.csv"
    cruzado.to_csv(caminhos["cruzado"], index=False, float_format="%.4f")
    decomposicao = pd.DataFrame([decompor(cruzado, "f1"), decompor(cruzado, "ap")])
    caminhos["decomposicao"] = args.saida / "decomposicao_variancia_if.csv"
    decomposicao.to_csv(caminhos["decomposicao"], index=False, float_format="%.4f")

    por_semente = pd.read_csv(args.entrada)
    caminhos["pareados"] = args.saida / "comparacoes_pareadas.csv"
    comparar(por_semente).to_csv(caminhos["pareados"], index=False, float_format="%.6g")

    caminhos["execucao"] = args.saida / "execucao.json"
    caminhos["execucao"].write_text(json.dumps({
        "executado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "sementes_base": list(SEMENTES_BASE),
        "random_states_isolation_forest": list(RANDOM_STATES),
        "n_bootstrap": N_BOOTSTRAP, "seed_bootstrap": SEED_BOOTSTRAP, "alfa": ALFA,
        "correcao_multiplas_comparacoes": "Holm, sobre todas as linhas de comparacoes_pareadas.csv",
        "entrada": str(args.entrada.relative_to(Path.cwd()) if args.entrada.is_relative_to(Path.cwd()) else args.entrada),
        "duracao_s": round(time.perf_counter() - inicio, 1),
        "versoes": {"python": platform.python_version(), "pandas": pd.__version__,
                    "numpy": np.__version__, "scikit-learn": sklearn.__version__,
                    "scipy": scipy.__version__},
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    for c in caminhos.values():
        print(f"Gravado: {c}")
    return caminhos


if __name__ == "__main__":
    main()
