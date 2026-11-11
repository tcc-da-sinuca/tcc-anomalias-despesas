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

Complementos da verificação de 11/11/2026:

3. **Todas as combinações e escolha fora da amostra** (item 2). Avalia as 11 uniões de dois
   ou mais métodos e a votação nas 20 bases, escolhe a de maior F1 médio nas sementes 1 a 10
   e confirma a escolha nas sementes 11 a 20, contra o Isolation Forest sozinho; essa
   comparação entra na correção de Holm.
4. **AP do Isolation Forest sem depender de um único random_state** (item 3): nas
   comparações de AP, o Isolation Forest entra com a média dos 20 valores de random_state
   de cada base.
5. **Z-score x IQR sem depender do limiar** (item 4): os dois são comparados pela AP e com
   a mesma proporção de despesas sinalizadas (os 5% de maior score de cada um).

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
from itertools import combinations

from motor import contextual, iqr, isolation_forest, zscore

PASTA = Path(__file__).resolve().parent / "resultados"
ENTRADA_POR_SEMENTE = PASTA / "robustez" / "por_semente.csv"
PASTA_SAIDA = PASTA / "testes_estatisticos"
SEMENTES_BASE = range(1, 21)
RANDOM_STATES = range(20)
N_BOOTSTRAP = 10_000
SEED_BOOTSTRAP = 42
ALFA = 0.05

METODOS = ("zscore", "iqr", "contextual", "isolation_forest")
PROPORCAO_FIXA = 0.05
SEMENTES_ESCOLHA = range(1, 11)
SEMENTES_CONFIRMACAO = range(11, 21)
IF_MEDIA_RS = "isolation_forest_media_rs"  # IF com a média dos 20 random_state de cada base
ESCOLHIDA = "melhor_combinacao_sementes_1a10"

# Pares comparados no texto do artigo: (avaliação A, avaliação B, métrica, motivo[, sementes]).
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
    (IF_MEDIA_RS, "iqr", "ap", "AP confirma a ordem sem limiar (IF: média de 20 random_state)"),
    (IF_MEDIA_RS, "zscore", "ap", "AP confirma a ordem sem limiar (IF: média de 20 random_state)"),
    ("zscore_robusto", "zscore", "ap", "z-score robusto x clássico"),
    ("zscore", "iqr", "ap", "univariados sem depender do limiar"),
    ("zscore_top5pct", "iqr_top5pct", "f1", "univariados com a mesma proporção sinalizada (5%)"),
    (ESCOLHIDA, "isolation_forest", "f1", "combinação escolhida nas sementes 1 a 10, confirmada nas 11 a 20",
     SEMENTES_CONFIRMACAO),
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


# --- 1b. Todas as combinações e proporção fixa ----------------------------------------


def todas_as_combinacoes() -> tuple[pd.DataFrame, pd.DataFrame]:
    """F1 por semente dos 4 métodos, das 11 uniões e da votação; e Z-score/IQR com 5% sinalizado."""
    linhas, fixa = [], []
    for seed in SEMENTES_BASE:
        base = gerar(seed)
        motor = {"zscore": _do_motor(zscore.detectar(base), base),
                 "iqr": _do_motor(iqr.detectar(base), base),
                 "contextual": _do_motor(contextual.detectar(base), base),
                 "isolation_forest": _do_motor(isolation_forest.detectar(base), base)}
        candidatos = {m: motor[m][1] for m in METODOS}
        for k in range(2, len(METODOS) + 1):
            for grupo in combinations(METODOS, k):
                candidatos["+".join(grupo)] = pd.concat([motor[m][1] for m in grupo], axis=1).any(axis=1)
        votos = pd.concat([motor[m][1] for m in METODOS], axis=1).sum(axis=1)
        candidatos["votacao_2"] = votos >= 2
        for nome, sinal in candidatos.items():
            l = linha(base, nome, "combinacao", None, sinal)
            linhas.append({"seed_base": seed, "avaliacao": nome, "n_metodos": nome.count("+") + 1
                           if nome != "votacao_2" else 4,
                           **{c: l[c] for c in ("precisao", "recall", "f1", "sinalizadas")}})
        k_fixo = int(round(PROPORCAO_FIXA * len(base)))
        for m in ("zscore", "iqr"):
            score = motor[m][0]
            sinal = pd.Series(False, index=base.index)
            sinal.loc[score.sort_values(ascending=False, kind="stable").index[:k_fixo]] = True
            l = linha(base, f"{m}_top5pct", "proporcao_fixa", score, sinal)
            fixa.append({"seed_base": seed, "avaliacao": f"{m}_top5pct",
                         **{c: l[c] for c in ("precisao", "recall", "f1", "sinalizadas", "ap")}})
    return pd.DataFrame(linhas), pd.DataFrame(fixa)


def escolher_combinacao(comb: pd.DataFrame) -> pd.DataFrame:
    """Ranking pelo F1 médio nas sementes de escolha e nas de confirmação."""
    escolha = comb[comb.seed_base.isin(SEMENTES_ESCOLHA)].groupby("avaliacao")["f1"].mean()
    confirma = comb[comb.seed_base.isin(SEMENTES_CONFIRMACAO)].groupby("avaliacao")["f1"].mean()
    todas = comb.groupby("avaliacao")["f1"].agg(["mean", "std"])
    tabela = pd.DataFrame({"f1_sementes_1a10": escolha, "f1_sementes_11a20": confirma,
                           "f1_media_20": todas["mean"], "f1_dp_20": todas["std"]})
    tabela["posicao_1a10"] = tabela["f1_sementes_1a10"].rank(ascending=False, method="min").astype(int)
    tabela["posicao_11a20"] = tabela["f1_sementes_11a20"].rank(ascending=False, method="min").astype(int)
    return tabela.sort_values("posicao_1a10").reset_index()


# --- 2. Comparação pareada -----------------------------------------------------------


def _ic_bootstrap(dif: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    amostras = rng.choice(dif, size=(N_BOOTSTRAP, dif.size), replace=True).mean(axis=1)
    return tuple(np.percentile(amostras, [2.5, 97.5]))


def comparar(por_semente: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(SEED_BOOTSTRAP)
    linhas = []
    for par in PARES:
        a, b, metrica, motivo = par[:4]
        sementes = par[4] if len(par) > 4 else None
        va = por_semente[por_semente.avaliacao == a].set_index("seed_base")[metrica]
        vb = por_semente[por_semente.avaliacao == b].set_index("seed_base")[metrica]
        comum = va.index.intersection(vb.index)
        if sementes is not None:
            comum = comum.intersection(pd.Index(list(sementes)))
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
            "sementes": f"{min(comum)} a {max(comum)}",
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

    comb, fixa = todas_as_combinacoes()
    caminhos["combinacoes"] = args.saida / "combinacoes_por_semente.csv"
    comb.to_csv(caminhos["combinacoes"], index=False, float_format="%.4f")
    caminhos["proporcao_fixa"] = args.saida / "zscore_iqr_proporcao_fixa.csv"
    fixa.to_csv(caminhos["proporcao_fixa"], index=False, float_format="%.4f")
    ranking = escolher_combinacao(comb)
    caminhos["escolha"] = args.saida / "escolha_da_combinacao.csv"
    ranking.to_csv(caminhos["escolha"], index=False, float_format="%.4f")
    escolhida = ranking.loc[ranking["posicao_1a10"] == 1, "avaliacao"].iloc[0]

    por_semente = pd.read_csv(args.entrada)
    media_rs = cruzado.groupby("seed_base")[["f1", "ap"]].mean().reset_index().assign(avaliacao=IF_MEDIA_RS)
    melhor = comb[comb.avaliacao == escolhida][["seed_base", "f1"]].assign(avaliacao=ESCOLHIDA)
    valores = pd.concat([por_semente, media_rs, fixa, melhor], ignore_index=True)
    caminhos["pareados"] = args.saida / "comparacoes_pareadas.csv"
    comparar(valores).to_csv(caminhos["pareados"], index=False, float_format="%.6g")

    caminhos["execucao"] = args.saida / "execucao.json"
    caminhos["execucao"].write_text(json.dumps({
        "executado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "sementes_base": list(SEMENTES_BASE),
        "random_states_isolation_forest": list(RANDOM_STATES),
        "n_bootstrap": N_BOOTSTRAP, "seed_bootstrap": SEED_BOOTSTRAP, "alfa": ALFA,
        "correcao_multiplas_comparacoes": "Holm, sobre todas as linhas de comparacoes_pareadas.csv",
        "combinacao_escolhida_sementes_1a10": escolhida,
        "proporcao_fixa_zscore_iqr": PROPORCAO_FIXA,
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
