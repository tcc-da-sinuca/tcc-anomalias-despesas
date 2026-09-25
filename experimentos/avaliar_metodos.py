"""Avaliação dos métodos de detecção na base sintética rotulada (seção 7 do CLAUDE.md).

Roda o motor direto sobre a base, sem banco nem Flask, e compara o que cada método
sinalizou com o rótulo ``anomalia_real``. A unidade de avaliação é a linha da base:
a despesa original de uma duplicada tem rótulo 0 e, se for sinalizada, conta como
falso positivo.

Avaliações:

- ``metodo``: cada método sozinho;
- ``uniao``: a despesa é sinalizada se qualquer método do conjunto sinalizar;
- ``votacao``: a despesa é sinalizada se pelo menos 2 métodos sinalizarem.

Saídas em ``experimentos/resultados/``:

- ``metricas.csv``: VP, FP, FN, VN, precisão, recall, F1 e taxa de FP de cada
  avaliação, com a seed da base e os parâmetros em cada linha;
- ``metricas_por_tipo.csv``: quantas linhas de cada tipo de anomalia (e das
  normais) cada avaliação sinalizou;
- ``execucao.json``: data, versões das bibliotecas, tempo de cada método e os
  metadados da base. Muda a cada execução; os CSVs só mudam se o código, a base
  ou os parâmetros mudarem.

Uso::

    python -m experimentos.avaliar_metodos
    python -m experimentos.avaliar_metodos --seed 7 --param zscore.limiar=2.5
    python -m experimentos.avaliar_metodos --arquivo dados/gerados/despesas_sinteticas.csv

Regra do projeto: nenhum número vai para o artigo sem ter saído deste script.
"""

import argparse
import json
import platform
import time
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn

from dados.gerar_base_sintetica import ConfiguracaoBase, gerar_base, metadados
from motor.consolidador import DETECTORES, parametros_padrao
from motor.estatisticas import DIMENSAO_DETECCAO, N_MINIMO_GRUPO

PASTA_RESULTADOS = Path(__file__).resolve().parent / "resultados"
VOTOS_MINIMOS = 2
TIPO_NORMAL = "normal"

COLUNAS_METRICAS = (
    "avaliacao",
    "nome",
    "metodos",
    "vp",
    "fp",
    "fn",
    "vn",
    "precisao",
    "recall",
    "f1",
    "taxa_fp",
    "sinalizadas",
    "seed_base",
    "parametros",
)
COLUNAS_POR_TIPO = ("avaliacao", "nome", "tipo_anomalia", "linhas", "sinalizadas", "taxa")


# --- Métricas -------------------------------------------------------------------


def _razao(numerador: int, denominador: int) -> float:
    """Divisão que devolve NaN quando o denominador é zero (métrica indefinida)."""
    return numerador / denominador if denominador else float("nan")


def metricas(real: pd.Series, previsto: pd.Series) -> dict[str, float | int]:
    """Matriz de confusão e métricas, com a classe positiva = anomalia.

    Precisão fica indefinida (NaN) quando nada foi sinalizado e recall, quando não
    há anomalias. F1 = 2·VP / (2·VP + FP + FN).
    """
    real = real.astype(bool).to_numpy()
    previsto = previsto.astype(bool).to_numpy()
    vp = int((real & previsto).sum())
    fp = int((~real & previsto).sum())
    fn = int((real & ~previsto).sum())
    vn = int((~real & ~previsto).sum())
    precisao = _razao(vp, vp + fp)
    recall = _razao(vp, vp + fn)
    return {
        "vp": vp,
        "fp": fp,
        "fn": fn,
        "vn": vn,
        "precisao": precisao,
        "recall": recall,
        "f1": _razao(2 * vp, 2 * vp + fp + fn),  # média harmônica de precisão e recall
        "taxa_fp": _razao(fp, fp + vn),
        "sinalizadas": vp + fp,
    }


# --- Avaliações (métodos e combinações) ----------------------------------------


def sinalizacoes(base: pd.DataFrame, resultados: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Uma coluna booleana por método, alinhada às linhas da base."""
    colunas = {}
    for metodo, resultado in resultados.items():
        por_id = resultado.set_index("despesa_id")["sinalizado"]
        colunas[metodo] = base["despesa_id"].map(por_id).fillna(False).astype(bool).to_numpy()
    return pd.DataFrame(colunas, index=base.index)


def avaliacoes(sinalizado: pd.DataFrame) -> list[tuple[str, str, list[str], pd.Series]]:
    """(avaliacao, nome, metodos, previsto) de cada método, união e votação."""
    metodos = list(sinalizado.columns)
    lista = [("metodo", m, [m], sinalizado[m]) for m in metodos]
    for tamanho in range(2, len(metodos) + 1):
        for grupo in combinations(metodos, tamanho):
            lista.append(
                ("uniao", "+".join(grupo), list(grupo), sinalizado[list(grupo)].any(axis=1))
            )
    if len(metodos) >= VOTOS_MINIMOS:
        votos = sinalizado.sum(axis=1) >= VOTOS_MINIMOS
        lista.append(("votacao", f">={VOTOS_MINIMOS} de {'+'.join(metodos)}", metodos, votos))
    return lista


def avaliar(
    base: pd.DataFrame,
    resultados: dict[str, pd.DataFrame],
    parametros: dict[str, dict],
    seed_base: int | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Tabelas de métricas gerais e por tipo de anomalia."""
    real = base["anomalia_real"].astype(int) == 1
    tipos = base["tipo_anomalia"].fillna("").replace("", TIPO_NORMAL)
    ordem_tipos = [t for t in sorted(tipos.unique()) if t != TIPO_NORMAL] + [TIPO_NORMAL]

    linhas_metricas, linhas_tipo = [], []
    for avaliacao, nome, metodos, previsto in avaliacoes(sinalizacoes(base, resultados)):
        usados = {m: parametros[m] for m in metodos}
        linhas_metricas.append(
            {
                "avaliacao": avaliacao,
                "nome": nome,
                "metodos": "+".join(metodos),
                **metricas(real, previsto),
                "seed_base": seed_base,
                "parametros": json.dumps(usados, sort_keys=True),
            }
        )
        for tipo in ordem_tipos:
            do_tipo = tipos == tipo
            quantas = int((previsto & do_tipo).sum())
            linhas_tipo.append(
                {
                    "avaliacao": avaliacao,
                    "nome": nome,
                    "tipo_anomalia": tipo,
                    "linhas": int(do_tipo.sum()),
                    "sinalizadas": quantas,
                    "taxa": _razao(quantas, int(do_tipo.sum())),
                }
            )
    return (
        pd.DataFrame(linhas_metricas, columns=list(COLUNAS_METRICAS)),
        pd.DataFrame(linhas_tipo, columns=list(COLUNAS_POR_TIPO)),
    )


def executar(
    base: pd.DataFrame, parametros: dict[str, dict], metodos: list[str]
) -> tuple[dict[str, pd.DataFrame], dict[str, float]]:
    """Roda cada detector e mede o tempo de cada um (RNF01, só para registro)."""
    resultados, tempos = {}, {}
    for metodo in metodos:
        inicio = time.perf_counter()
        resultados[metodo] = DETECTORES[metodo](base, **parametros[metodo])
        tempos[metodo] = round(time.perf_counter() - inicio, 4)
    return resultados, tempos


# --- Entrada e saída --------------------------------------------------------------


def carregar_base(arquivo: Path | None, seed: int) -> tuple[pd.DataFrame, dict | None]:
    """Base no formato do motor, mais os metadados quando ela é gerada agora."""
    if arquivo is None:
        config = ConfiguracaoBase(seed=seed)
        base = gerar_base(config)
        info = metadados(base, config)
    else:
        base = pd.read_csv(arquivo, dtype={"conta_contabil": str}, keep_default_na=False)
        info = None
    base = base.rename(columns={"id_sintetico": "despesa_id"})
    base["valor"] = base["valor"].astype(float)
    base["data"] = pd.to_datetime(base["data"])
    return base, info


def ler_parametros(atribuicoes: list[str], metodos: list[str]) -> dict[str, dict]:
    """Padrões do motor com as alterações ``metodo.chave=valor`` da linha de comando."""
    parametros = parametros_padrao(metodos)
    for atribuicao in atribuicoes:
        try:
            alvo, valor = atribuicao.split("=", 1)
            metodo, chave = alvo.split(".", 1)
        except ValueError:
            raise SystemExit(f"--param inválido: {atribuicao!r}. Use metodo.chave=valor.") from None
        if metodo not in parametros or chave not in parametros[metodo]:
            raise SystemExit(f"Parâmetro desconhecido: {alvo}.")
        tipo = type(parametros[metodo][chave])
        parametros[metodo][chave] = tipo(valor)
    return parametros


def salvar(
    pasta: Path, metricas_gerais: pd.DataFrame, por_tipo: pd.DataFrame, execucao: dict
) -> dict[str, Path]:
    pasta.mkdir(parents=True, exist_ok=True)
    caminhos = {
        "metricas": pasta / "metricas.csv",
        "por_tipo": pasta / "metricas_por_tipo.csv",
        "execucao": pasta / "execucao.json",
    }
    metricas_gerais.to_csv(
        caminhos["metricas"], index=False, float_format="%.4f", lineterminator="\n"
    )
    por_tipo.to_csv(caminhos["por_tipo"], index=False, float_format="%.4f", lineterminator="\n")
    caminhos["execucao"].write_text(
        json.dumps(execucao, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return caminhos


def main(argv: list[str] | None = None) -> dict[str, Path]:
    parser = argparse.ArgumentParser(description="Avalia os métodos de detecção na base sintética.")
    parser.add_argument("--seed", type=int, default=42, help="Seed da base gerada (padrão: 42).")
    parser.add_argument("--arquivo", type=Path, help="CSV rotulado, em vez de gerar a base.")
    parser.add_argument(
        "--metodo",
        dest="metodos",
        action="append",
        choices=list(DETECTORES),
        help="Método a avaliar (repetível). Padrão: todos.",
    )
    parser.add_argument(
        "--param",
        dest="params",
        action="append",
        default=[],
        help="Altera um parâmetro: metodo.chave=valor (repetível).",
    )
    parser.add_argument("--saida", type=Path, default=PASTA_RESULTADOS, help="Pasta de resultados.")
    args = parser.parse_args(argv)

    metodos = args.metodos or list(DETECTORES)
    parametros = ler_parametros(args.params, metodos)
    base, info_base = carregar_base(args.arquivo, args.seed)
    seed_base = args.seed if args.arquivo is None else None

    resultados, tempos = executar(base, parametros, metodos)
    metricas_gerais, por_tipo = avaliar(base, resultados, parametros, seed_base)

    execucao = {
        "executado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "base": str(args.arquivo) if args.arquivo else f"gerada com seed {args.seed}",
        "seed_base": seed_base,
        "metodos": metodos,
        "parametros": parametros,
        "dimensao_valor": DIMENSAO_DETECCAO,
        "n_minimo_grupo": N_MINIMO_GRUPO,
        "votos_minimos": VOTOS_MINIMOS,
        "tempo_s_por_metodo": tempos,
        "linhas": len(base),
        "versoes": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "scikit-learn": sklearn.__version__,
        },
        "metadados_base": info_base,
    }
    caminhos = salvar(args.saida, metricas_gerais, por_tipo, execucao)

    colunas = ["nome", "precisao", "recall", "f1", "taxa_fp", "sinalizadas"]
    print(metricas_gerais[colunas].to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    for caminho in caminhos.values():
        print(f"Gravado: {caminho}")
    return caminhos


if __name__ == "__main__":
    main()
