"""Experimento ampliado: robustez, linhas de base, ablação e ameaças à validade.

Complementa ``avaliar_metodos.py`` (que continua sendo o resultado principal, seeds 42 e
7) com os pontos levantados na verificação do orientador de 08/10/2026:

- **várias sementes** da base (média e desvio padrão), em vez de só duas;
- **área sob a curva precisão-revocação** (precisão média, AP) de cada método, que não
  depende de um limiar;
- desempenho em **vários valores de contamination** (Isolation Forest) e de limiar
  (Z-score e IQR);
- **linhas de base** simples (sinalização aleatória e "5% maiores valores da categoria") e
  um Isolation Forest sobre os **atributos brutos**, para medir o ganho dos atributos
  derivados;
- **ablação** dos atributos derivados do Isolation Forest;
- variantes do Z-score e do IQR com **logaritmo do valor** e o **z-score robusto**
  (mediana e MAD);
- **cenários de estresse** que afastam a geração das anomalias das hipóteses dos
  detectores, para medir o risco de circularidade (anomalias "acertadas por construção").

Roda o motor direto, sem banco nem Flask, como o experimento principal. Nenhum parâmetro
da aplicação muda: as variantes existem só aqui, para comparação.

Uso::

    python -m experimentos.avaliar_robustez                     # 20 sementes (1 a 20)
    python -m experimentos.avaliar_robustez --sementes 5        # rápido, para testar

Saída em ``experimentos/resultados/robustez/`` (um CSV por análise e ``execucao.json``).
Regra do projeto: nenhum número vai para o artigo sem ter saído de uma execução real.
"""

import argparse
import json
import platform
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score

import dados.gerar_base_sintetica as gerador
from experimentos.avaliar_metodos import metricas
from motor import contextual, iqr, isolation_forest, zscore
from motor.estatisticas import DIMENSAO_DETECCAO, DIMENSAO_RECUO, N_MINIMO_GRUPO

PASTA_SAIDA = Path(__file__).resolve().parent / "resultados" / "robustez"
SEMENTES_PADRAO = 20
RANDOM_STATE_IF = 42
CONTAMINATIONS = (0.01, 0.02, 0.03, 0.04, 0.05, 0.075, 0.10, 0.15)
LIMIARES_Z = (2.0, 2.5, 3.0, 3.5, 4.0)
FATORES_IQR = (1.5, 2.0, 3.0)
LIMIAR_Z_ROBUSTO = 3.5  # Iglewicz e Hoaglin (1993)
FRACAO_FIM_SEMANA_LEGITIMO = 0.05


# --- Base ----------------------------------------------------------------------------


def gerar(seed: int) -> pd.DataFrame:
    base = gerador.gerar_base(gerador.ConfiguracaoBase(seed=seed))
    base = base.rename(columns={"id_sintetico": "despesa_id"})
    base["valor"] = base["valor"].astype(float)
    base["data"] = pd.to_datetime(base["data"])
    return base


@contextmanager
def constantes_do_gerador(**valores):
    """Troca temporariamente constantes do gerador (cenários de estresse)."""
    antigas = {nome: getattr(gerador, nome) for nome in valores}
    try:
        for nome, valor in valores.items():
            setattr(gerador, nome, valor)
        yield
    finally:
        for nome, valor in antigas.items():
            setattr(gerador, nome, valor)


def com_fim_semana_legitimo(base: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Leva 5% das despesas normais para o sábado ou domingo vizinho, mantendo o rótulo 0.

    Numa empresa real há despesas legítimas fora dos dias úteis (viagens, plantões), o que
    a base sintética não tem: lá, toda despesa em fim de semana é anomalia.
    """
    rng = np.random.default_rng(seed + 10_000)
    base = base.copy()
    normais = base.index[(base["anomalia_real"] == 0) & (base["grupo_anomalia"] == "")]
    escolhidas = rng.choice(normais, size=int(len(normais) * FRACAO_FIM_SEMANA_LEGITIMO), replace=False)
    datas = base.loc[escolhidas, "data"]
    ate_sabado = (5 - datas.dt.dayofweek) % 7
    base.loc[escolhidas, "data"] = datas + pd.to_timedelta(ate_sabado + rng.integers(0, 2, len(datas)), unit="D")
    return base


CENARIOS = {
    "padrao": {"constantes": {}, "fim_semana_legitimo": False,
               "descricao": "Base padrão (hipóteses da geração = hipóteses dos detectores)"},
    "extremo_sutil": {"constantes": {"FATOR_EXTREMO": (2.5, 4.0)}, "fim_semana_legitimo": False,
                      "descricao": "Valor extremo de 2,5 a 4 vezes a mediana (em vez de 5 a 15)"},
    "duplicada_tardia": {"constantes": {"ATRASO_DUPLICADA_DIAS": (6, 12)}, "fim_semana_legitimo": False,
                         "descricao": "Duplicada de 6 a 12 dias úteis depois (fora da janela de 7 dias corridos)"},
    "fracionamento_baixo": {"constantes": {"FAIXA_FRACIONAMENTO": (0.60, 0.84)}, "fim_semana_legitimo": False,
                            "descricao": "Fracionamento entre 60% e 84% do limite (fora da faixa de 85%)"},
    "fim_semana_legitimo": {"constantes": {}, "fim_semana_legitimo": True,
                            "descricao": "5% das despesas normais em fim de semana (legítimas)"},
    "todos": {"constantes": {"FATOR_EXTREMO": (2.5, 4.0), "ATRASO_DUPLICADA_DIAS": (6, 12),
                             "FAIXA_FRACIONAMENTO": (0.60, 0.84)}, "fim_semana_legitimo": True,
              "descricao": "Todas as perturbações acima ao mesmo tempo"},
}


def gerar_cenario(nome: str, seed: int) -> pd.DataFrame:
    cenario = CENARIOS[nome]
    with constantes_do_gerador(**cenario["constantes"]):
        base = gerar(seed)
    if cenario["fim_semana_legitimo"]:
        base = com_fim_semana_legitimo(base, seed)
    return base


# --- Variantes e linhas de base (só para comparação) ----------------------------------


def _grupo(despesas: pd.DataFrame, valores: pd.Series, estatistica) -> pd.Series:
    """Estatística do grupo centro de custo × conta, com recuo para a categoria (n < 10)."""
    chave = [despesas[c] for c in DIMENSAO_DETECCAO]
    n = valores.groupby(chave).transform("size")
    principal = valores.groupby(chave).transform(estatistica)
    recuo = valores.groupby(despesas[DIMENSAO_RECUO]).transform(estatistica)
    n_recuo = valores.groupby(despesas[DIMENSAO_RECUO]).transform("size")
    resultado = principal.where(n >= N_MINIMO_GRUPO, recuo)
    return resultado.where((n >= N_MINIMO_GRUPO) | (n_recuo >= N_MINIMO_GRUPO))


def zscore_log(despesas: pd.DataFrame, limiar: float = 3.0) -> tuple[pd.Series, pd.Series]:
    logs = np.log(despesas["valor"].astype(float).clip(lower=0.01))
    media, desvio = _grupo(despesas, logs, "mean"), _grupo(despesas, logs, "std")
    score = ((logs - media) / desvio).abs().where(desvio > 0, 0.0).fillna(0.0)
    return score, score > limiar


def zscore_robusto(despesas: pd.DataFrame, limiar: float = LIMIAR_Z_ROBUSTO, usar_log=False):
    """|0,6745 · (x − mediana) / MAD| (Iglewicz; Hoaglin, 1993)."""
    valores = despesas["valor"].astype(float)
    if usar_log:
        valores = np.log(valores.clip(lower=0.01))
    mediana = _grupo(despesas, valores, "median")
    desvios = (valores - mediana).abs()
    mad = _grupo(despesas.assign(), desvios, "median")
    score = (0.6745 * (valores - mediana) / mad).abs().where(mad > 0, 0.0).fillna(0.0)
    return score, score > limiar


def iqr_log(despesas: pd.DataFrame, fator: float = 1.5):
    logs = np.log(despesas["valor"].astype(float).clip(lower=0.01))
    q1 = _grupo(despesas, logs, lambda v: v.quantile(0.25))
    q3 = _grupo(despesas, logs, lambda v: v.quantile(0.75))
    amplitude = q3 - q1
    score = pd.concat([(logs - q3) / amplitude, (q1 - logs) / amplitude], axis=1).max(axis=1)
    score = score.clip(lower=0).where(amplitude > 0, 0.0).fillna(0.0)
    return score, score > fator


def maiores_da_categoria(despesas: pd.DataFrame, fracao: float = 0.05):
    """Linha de base: sinaliza os 5% maiores valores de cada categoria."""
    posto = despesas.groupby("categoria")["valor"].rank(pct=True)
    return posto, posto > 1 - fracao


def aleatorio(despesas: pd.DataFrame, seed: int, fracao: float = 0.05):
    rng = np.random.default_rng(seed + 20_000)
    score = pd.Series(rng.random(len(despesas)), index=despesas.index)
    return score, score > 1 - fracao


def isolation_forest_bruto(despesas: pd.DataFrame, contamination=0.05, random_state=RANDOM_STATE_IF):
    """Isolation Forest sobre os atributos brutos do lançamento, sem atributos derivados.

    Valor (em log), dia da semana, dia do mês, mês e os códigos de categoria, conta,
    centro de custo e funcionário: o que se usaria sem conhecer os tipos de anomalia.
    """
    datas = pd.to_datetime(despesas["data"])
    matriz = np.column_stack(
        [np.log(despesas["valor"].astype(float).clip(lower=0.01)), datas.dt.dayofweek,
         datas.dt.day, datas.dt.month]
        + [pd.factorize(despesas[c])[0] for c in ("categoria", "conta_contabil", "centro_custo", "funcionario")]
    ).astype(float)
    modelo = IsolationForest(n_estimators=isolation_forest.N_ARVORES, contamination=contamination,
                             random_state=random_state).fit(matriz)
    score = pd.Series(-modelo.score_samples(matriz), index=despesas.index)
    return score, pd.Series(modelo.predict(matriz) == -1, index=despesas.index)


def isolation_forest_atributos(despesas, usar, contamination=0.05, random_state=RANDOM_STATE_IF,
                               limite_aprovacao=1000.0):
    """Isolation Forest só com os atributos derivados de ``usar`` (ablação)."""
    tabela = isolation_forest.atributos(despesas, limite_aprovacao)
    matriz = tabela[list(usar)].to_numpy(dtype=float)
    modelo = IsolationForest(n_estimators=isolation_forest.N_ARVORES, contamination=contamination,
                             random_state=random_state).fit(matriz)
    score = pd.Series(-modelo.score_samples(matriz), index=despesas.index)
    return score, pd.Series(modelo.predict(matriz) == -1, index=despesas.index)


# --- Avaliação -------------------------------------------------------------------------


def _do_motor(resultado: pd.DataFrame, base: pd.DataFrame):
    r = resultado.set_index("despesa_id").loc[base["despesa_id"]]
    return pd.Series(r["score"].to_numpy(), index=base.index), pd.Series(r["sinalizado"].to_numpy(), index=base.index)


def linha(base, nome, grupo, score, sinalizado, **extra) -> dict:
    real = base["anomalia_real"].astype(int) == 1
    m = metricas(real, sinalizado)
    ap = average_precision_score(real, score) if score is not None else float("nan")
    tipos = base["tipo_anomalia"].replace("", "normal")
    por_tipo = {f"recall_{t}": float(sinalizado[tipos == t].mean())
                for t in gerador.TIPOS_ANOMALIA if (tipos == t).any()}
    return {"grupo": grupo, "avaliacao": nome, **extra, **m, "ap": ap,
            "prevalencia": float(real.mean()), **por_tipo}


def avaliar_base(base: pd.DataFrame, seed: int, completo: bool = True) -> list[dict]:
    """Métodos do motor, combinações, variantes, linhas de base e ablação numa base."""
    motor = {
        "zscore": _do_motor(zscore.detectar(base), base),
        "iqr": _do_motor(iqr.detectar(base), base),
        "contextual": _do_motor(contextual.detectar(base), base),
        "isolation_forest": _do_motor(isolation_forest.detectar(base), base),
    }
    linhas = [linha(base, m, "motor", s, f) for m, (s, f) in motor.items()]
    combinacoes = {
        "contextual+isolation_forest": ["contextual", "isolation_forest"],
        "zscore+contextual+isolation_forest": ["zscore", "contextual", "isolation_forest"],
        "uniao_quatro": list(motor),
    }
    for nome, metodos in combinacoes.items():
        linhas.append(linha(base, nome, "combinacao", None,
                            pd.concat([motor[m][1] for m in metodos], axis=1).any(axis=1)))
    votos = pd.concat([f for _, f in motor.values()], axis=1).sum(axis=1)
    linhas.append(linha(base, "votacao_2", "combinacao", votos, votos >= 2))
    if not completo:
        return linhas

    variantes = {
        "zscore_log": zscore_log(base),
        "zscore_robusto": zscore_robusto(base),
        "zscore_robusto_log": zscore_robusto(base, usar_log=True),
        "iqr_log": iqr_log(base),
    }
    linhas += [linha(base, n, "variante", s, f) for n, (s, f) in variantes.items()]
    linhas.append(linha(base, "aleatorio_5pct", "linha_de_base", *aleatorio(base, seed)))
    linhas.append(linha(base, "maiores_5pct_categoria", "linha_de_base", *maiores_da_categoria(base)))
    linhas.append(linha(base, "isolation_forest_bruto", "linha_de_base", *isolation_forest_bruto(base)))

    todos = isolation_forest.ATRIBUTOS
    for retirado in todos:
        usar = [a for a in todos if a != retirado]
        linhas.append(linha(base, f"if_sem_{retirado}", "ablacao", *isolation_forest_atributos(base, usar)))
    linhas.append(linha(base, "if_so_desvio_valor", "ablacao",
                        *isolation_forest_atributos(base, ["desvio_valor"])))
    return linhas


def resumir(tabela: pd.DataFrame, chaves: list[str]) -> pd.DataFrame:
    colunas = ["precisao", "recall", "f1", "taxa_fp", "ap", "sinalizadas"]
    colunas += [c for c in tabela.columns if c.startswith("recall_")]
    agregado = tabela.groupby(chaves, sort=False)[colunas].agg(["mean", "std"])
    agregado.columns = [f"{c}_{e}" for c, e in agregado.columns]
    agregado.insert(0, "n_sementes", tabela.groupby(chaves, sort=False).size())
    return agregado.reset_index()


def main(argv: list[str] | None = None) -> dict[str, Path]:
    parser = argparse.ArgumentParser(description="Experimento ampliado (robustez e validade).")
    parser.add_argument("--sementes", type=int, default=SEMENTES_PADRAO,
                        help="Quantidade de sementes da base, de 1 a N (padrão: 20).")
    parser.add_argument("--saida", type=Path, default=PASTA_SAIDA)
    args = parser.parse_args(argv)
    sementes = list(range(1, args.sementes + 1))
    inicio = time.perf_counter()
    args.saida.mkdir(parents=True, exist_ok=True)
    caminhos = {}

    # 1. Várias sementes: motor, combinações, variantes, linhas de base, ablação.
    linhas = []
    for seed in sementes:
        base = gerar(seed)
        linhas += [{"seed_base": seed, **l} for l in avaliar_base(base, seed)]
    por_semente = pd.DataFrame(linhas)
    caminhos["por_semente"] = args.saida / "por_semente.csv"
    por_semente.to_csv(caminhos["por_semente"], index=False, float_format="%.4f")
    caminhos["resumo"] = args.saida / "resumo_sementes.csv"
    resumir(por_semente, ["grupo", "avaliacao"]).to_csv(caminhos["resumo"], index=False, float_format="%.4f")

    # 2. Semente do Isolation Forest variando, com a base fixa (seed 42).
    base42 = gerar(42)
    linhas = []
    for rs in range(20):
        s, f = _do_motor(isolation_forest.detectar(base42, random_state=rs), base42)
        linhas.append({"random_state": rs, **linha(base42, "isolation_forest", "motor", s, f)})
    caminhos["random_state_if"] = args.saida / "random_state_if.csv"
    pd.DataFrame(linhas).to_csv(caminhos["random_state_if"], index=False, float_format="%.4f")

    # 3. Sensibilidade ao limiar: contamination, limiar do Z-score e fator do IQR.
    linhas = []
    for seed in sementes:
        base = gerar(seed)
        ctx = _do_motor(contextual.detectar(base), base)[1]
        for c in CONTAMINATIONS:
            s, f = _do_motor(isolation_forest.detectar(base, contamination=c), base)
            linhas.append({"seed_base": seed, "parametro": "contamination", "valor": c,
                           **linha(base, "isolation_forest", "limiar", s, f)})
            linhas.append({"seed_base": seed, "parametro": "contamination", "valor": c,
                           **linha(base, "contextual+isolation_forest", "limiar", None, f | ctx)})
        for z in LIMIARES_Z:
            s, f = _do_motor(zscore.detectar(base, limiar=z), base)
            linhas.append({"seed_base": seed, "parametro": "limiar_z", "valor": z,
                           **linha(base, "zscore", "limiar", s, f)})
        for k in FATORES_IQR:
            s, f = _do_motor(iqr.detectar(base, fator=k), base)
            linhas.append({"seed_base": seed, "parametro": "fator_iqr", "valor": k,
                           **linha(base, "iqr", "limiar", s, f)})
    sensibilidade = pd.DataFrame(linhas)
    caminhos["sensibilidade"] = args.saida / "sensibilidade_limiar.csv"
    resumir(sensibilidade, ["avaliacao", "parametro", "valor"]).to_csv(
        caminhos["sensibilidade"], index=False, float_format="%.4f")

    # 4. Cenários de estresse (circularidade).
    linhas = []
    for nome in CENARIOS:
        for seed in sementes[:10]:
            base = gerar_cenario(nome, seed)
            linhas += [{"cenario": nome, "seed_base": seed, **l}
                       for l in avaliar_base(base, seed, completo=False)]
    estresse = pd.DataFrame(linhas)
    caminhos["estresse"] = args.saida / "cenarios_estresse.csv"
    resumir(estresse, ["cenario", "avaliacao"]).to_csv(caminhos["estresse"], index=False, float_format="%.4f")

    execucao = {
        "executado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "sementes_base": sementes,
        "sementes_estresse": sementes[:10],
        "random_state_isolation_forest": RANDOM_STATE_IF,
        "contaminations": CONTAMINATIONS, "limiares_z": LIMIARES_Z, "fatores_iqr": FATORES_IQR,
        "limiar_z_robusto": LIMIAR_Z_ROBUSTO,
        "cenarios": {n: c["descricao"] for n, c in CENARIOS.items()},
        "duracao_s": round(time.perf_counter() - inicio, 1),
        "versoes": {"python": platform.python_version(), "pandas": pd.__version__,
                    "numpy": np.__version__, "scikit-learn": sklearn.__version__},
    }
    caminhos["execucao"] = args.saida / "execucao.json"
    caminhos["execucao"].write_text(json.dumps(execucao, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for c in caminhos.values():
        print(f"Gravado: {c}")
    return caminhos


if __name__ == "__main__":
    main()
