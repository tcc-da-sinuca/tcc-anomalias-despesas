"""Detector Isolation Forest com atributos derivados (RF04 / US04).

Cobre as anomalias que os outros métodos não pegam: despesa duplicada,
fracionamento logo abaixo do limite de aprovação e lançamento em fim de semana ou
feriado (docs/ISOLATION_FOREST.md). O modelo não olha a despesa isolada, e sim
quatro atributos calculados em relação às outras despesas:

- ``desvio_valor``: |z| do logaritmo do valor dentro da categoria;
- ``fim_semana_feriado``: 1 se sábado, domingo ou feriado nacional;
- ``repeticoes_valor``: outras despesas do mesmo funcionário, categoria e valor em
  até ``JANELA_REPETICAO_DIAS`` dias;
- ``fracionamento``: se o valor está na faixa logo abaixo do limite, outras despesas
  do mesmo funcionário na mesma faixa em até ``JANELA_FRACIONAMENTO_DIAS`` dias.

Score = ``-score_samples`` (maior = mais isolada). Sinaliza as despesas que o modelo
classifica como anômalas (proporção ``contamination``). O motivo é montado a partir
dos atributos ativos da despesa, porque o Isolation Forest não explica o que isolou.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from motor import texto
from motor.calendario import eh_feriado
from motor.contrato import montar_resultado, resultado_vazio
from motor.estatisticas import (
    DIMENSAO_DETECCAO,
    DIMENSAO_RECUO,
    N_MINIMO_GRUPO,
    descrever_grupo,
    estatisticas_por_despesa,
)

# Constantes fixadas pela definição das anomalias, não ajustadas pelo experimento.
JANELA_REPETICAO_DIAS = 7
JANELA_FRACIONAMENTO_DIAS = 5
FAIXA_LIMITE = 0.85  # "logo abaixo do limite": de 85% a 100% dele
DESVIO_VALOR_MOTIVO = 2.5  # a partir daqui o motivo cita o valor
N_ARVORES = 100
ATRIBUTOS = ("desvio_valor", "fim_semana_feriado", "repeticoes_valor", "fracionamento")

DIAS_SEMANA = {5: "num sábado", 6: "num domingo"}


def _vizinhos_na_janela(datas: np.ndarray, grupos: np.ndarray, janela: int) -> np.ndarray:
    """Para cada posição, quantas outras do mesmo grupo estão a até ``janela`` dias."""
    contagem = np.zeros(len(datas), dtype=int)
    for posicoes in pd.Series(np.arange(len(datas))).groupby(grupos).indices.values():
        if len(posicoes) < 2:
            continue
        dias = datas[posicoes]
        proximas = np.abs(dias[:, None] - dias[None, :]) <= janela
        contagem[posicoes] = proximas.sum(axis=1) - 1
    return contagem


def atributos(despesas: pd.DataFrame, limite_aprovacao: float = 1000.0) -> pd.DataFrame:
    """Tabela com os ``ATRIBUTOS`` de cada despesa, alinhada ao índice de ``despesas``.

    Inclui também ``z_log_valor`` (com sinal) e ``usa_recuo``, usados no motivo. O
    desvio do valor é medido no grupo centro de custo × conta, com recuo para a categoria.
    """
    valores = despesas["valor"].astype(float)
    datas = pd.to_datetime(despesas["data"])
    dias = datas.to_numpy().astype("datetime64[D]").astype(np.int64)

    logs = np.log(valores.clip(lower=0.01))
    grupo = estatisticas_por_despesa(despesas.assign(valor=logs), DIMENSAO_DETECCAO, DIMENSAO_RECUO)
    avaliavel = (grupo["n"] >= N_MINIMO_GRUPO) & (grupo["desvio"] > 0)
    z_log = ((logs - grupo["media"]) / grupo["desvio"]).where(avaliavel, 0.0)

    fim_semana_feriado = (datas.dt.dayofweek >= 5) | datas.dt.date.map(eh_feriado)

    chave_repeticao = (
        despesas["funcionario"].astype(str)
        + "|"
        + despesas["categoria"].astype(str)
        + "|"
        + valores.round(2).astype(str)
    ).to_numpy()
    repeticoes = _vizinhos_na_janela(dias, chave_repeticao, JANELA_REPETICAO_DIAS)

    na_faixa = (
        (valores >= FAIXA_LIMITE * limite_aprovacao) & (valores < limite_aprovacao)
    ).to_numpy()
    fracionamento = np.zeros(len(despesas), dtype=int)
    if na_faixa.any():
        fracionamento[na_faixa] = _vizinhos_na_janela(
            dias[na_faixa],
            despesas["funcionario"].astype(str).to_numpy()[na_faixa],
            JANELA_FRACIONAMENTO_DIAS,
        )

    return pd.DataFrame(
        {
            "desvio_valor": z_log.abs().to_numpy(),
            "fim_semana_feriado": fim_semana_feriado.astype(int).to_numpy(),
            "repeticoes_valor": repeticoes,
            "fracionamento": fracionamento,
            "z_log_valor": z_log.to_numpy(),
            "usa_recuo": grupo["usa_recuo"].to_numpy(),
        },
        index=despesas.index,
    )


def detectar(
    despesas: pd.DataFrame,
    contamination: float = 0.05,
    random_state: int = 42,
    limite_aprovacao: float = 1000.0,
) -> pd.DataFrame:
    """Score de isolamento de cada despesa a partir dos atributos derivados. Ver ``motor.contrato``.

    Com menos de ``N_MINIMO_GRUPO`` despesas o modelo não é treinado (score 0).
    """
    if despesas.empty:
        return resultado_vazio()
    tabela = atributos(despesas, limite_aprovacao)
    if len(despesas) < N_MINIMO_GRUPO:
        zeros = pd.Series(0.0, index=despesas.index)
        return montar_resultado(despesas, zeros, zeros.astype(bool), zeros.astype(str))

    matriz = tabela[list(ATRIBUTOS)].to_numpy(dtype=float)
    modelo = IsolationForest(
        n_estimators=N_ARVORES, contamination=contamination, random_state=int(random_state)
    ).fit(matriz)
    score = pd.Series(-modelo.score_samples(matriz), index=despesas.index)
    sinalizado = pd.Series(modelo.predict(matriz) == -1, index=despesas.index)

    motivos = pd.Series("", index=despesas.index, dtype=object)
    for i in despesas.index[sinalizado]:
        motivos[i] = _motivo(despesas.loc[i], tabela.loc[i], limite_aprovacao)
    return montar_resultado(despesas, score, sinalizado, motivos)


def _vezes(quantidade: int, singular: str, plural: str) -> str:
    return f"{quantidade} {singular if quantidade == 1 else plural}"


def _motivo(despesa: pd.Series, atributo: pd.Series, limite_aprovacao: float) -> str:
    """Uma frase por atributo ativo, na ordem de ``ATRIBUTOS`` (decisão D8)."""
    valor = float(despesa["valor"])
    data = pd.Timestamp(despesa["data"])
    frases = []

    if atributo["desvio_valor"] > DESVIO_VALOR_MOTIVO:
        direcao = "acima" if atributo["z_log_valor"] > 0 else "abaixo"
        frases.append(
            f"Valor {texto.moeda(valor)} muito {direcao} do habitual "
            f"{descrever_grupo(despesa, DIMENSAO_DETECCAO, DIMENSAO_RECUO, atributo['usa_recuo'])}."
        )
    if atributo["fim_semana_feriado"]:
        dia = data.strftime("%d/%m/%Y")
        if eh_feriado(data.date()):
            frases.append(f"Lançada em feriado nacional ({dia}).")
        else:
            frases.append(f"Lançada {DIAS_SEMANA[data.dayofweek]} ({dia}).")
    if atributo["repeticoes_valor"] > 0:
        frases.append(
            f"O funcionário {despesa['funcionario']} lançou o mesmo valor ({texto.moeda(valor)}) "
            f"na categoria {despesa['categoria']} mais "
            f"{_vezes(int(atributo['repeticoes_valor']), 'vez', 'vezes')} "
            f"em até {JANELA_REPETICAO_DIAS} dias."
        )
    if atributo["fracionamento"] > 0:
        frases.append(
            f"Valor {texto.moeda(valor)} entre {texto.percentual(FAIXA_LIMITE)} e 100% do limite "
            f"de {texto.moeda(limite_aprovacao)}, com mais "
            f"{_vezes(int(atributo['fracionamento']), 'lançamento', 'lançamentos')} do "
            f"funcionário {despesa['funcionario']} na mesma faixa em até "
            f"{JANELA_FRACIONAMENTO_DIAS} dias (possível fracionamento)."
        )
    if not frases:
        return (
            "Combinação incomum de valor, data e frequência de lançamentos, sem um fator "
            "isolado que explique; revise o contexto da despesa."
        )
    return " ".join(frases)
