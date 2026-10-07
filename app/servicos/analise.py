"""Serviço de análise: executa o motor e grava a execução e os alertas (RF03–RF05, RF12).

Fluxo descrito em docs/FLUXO_ANALISE.md, seção 3:

1. lê os parâmetros dos métodos;
2. carrega todas as despesas, porque as estatísticas dos grupos dependem da base toda;
3. roda os detectores e consolida os sinalizados (um alerta por despesa e método);
4. descarta os que já têm alerta do mesmo método, de qualquer execução anterior,
   para que reexecutar não duplique alertas;
5. grava a ``ExecucaoAnalise`` (parâmetros, seed, totais, duração) e os
   ``AlertaAnomalia`` como ``pendente``.

Não faz commit; quem chama (rota, comando ou job) decide.
"""

import time
from collections.abc import Iterable

import pandas as pd
from sqlalchemy import insert, select, text

from app.extensoes import db
from app.models import AlertaAnomalia, Despesa, ExecucaoAnalise, Usuario
from app.models.base import agora_utc
from app.models.dominio import METODO_ISOLATION_FOREST, STATUS_PENDENTE
from app.servicos.parametros import obter_parametros
from motor.consolidador import DETECTORES, MetodoDesconhecidoError, consolidar, executar_detectores
from motor.contrato import COLUNAS_ENTRADA
from motor.estatisticas import DIMENSAO_DETECCAO, N_MINIMO_GRUPO

__all__ = ["MetodoDesconhecidoError", "carregar_despesas", "executar_analise"]

# Identificador da trava de análise no PostgreSQL (pg_advisory_xact_lock).
CHAVE_TRAVA = 4_906_001


def carregar_despesas() -> pd.DataFrame:
    """Todas as despesas no formato de entrada do motor (``motor.contrato``)."""
    colunas = [Despesa.id.label("despesa_id"), *(getattr(Despesa, c) for c in COLUNAS_ENTRADA[1:])]
    linhas = db.session.execute(select(*colunas).order_by(Despesa.id)).all()
    despesas = pd.DataFrame(linhas, columns=list(COLUNAS_ENTRADA))
    # float só para o cálculo; o valor persistido continua Numeric.
    despesas["valor"] = despesas["valor"].astype(float)
    despesas["data"] = pd.to_datetime(despesas["data"])
    return despesas


def executar_analise(
    usuario: Usuario | None, metodos: Iterable[str] | None = None
) -> ExecucaoAnalise:
    """Roda o motor sobre todas as despesas e grava a execução e os alertas novos.

    ``usuario`` vazio indica execução por job agendado. ``metodos`` vazio roda
    todos os detectores disponíveis. Levanta ``MetodoDesconhecidoError`` para um
    método sem detector.
    """
    metodos = list(DETECTORES) if metodos is None else list(dict.fromkeys(metodos))
    _travar_analise()
    inicio = time.perf_counter()
    iniciada_em = agora_utc()

    parametros = obter_parametros()
    despesas = carregar_despesas()
    alertas = consolidar(executar_detectores(despesas, parametros, metodos))
    alertas = _sem_alertas_existentes(alertas)

    execucao = ExecucaoAnalise(
        iniciada_em=iniciada_em,
        parametros=_parametros_registrados(parametros, metodos),
        seed=int(parametros[METODO_ISOLATION_FOREST]["random_state"]),
        total_despesas=len(despesas),
        total_alertas=len(alertas),
        executada_por=usuario.id if usuario is not None else None,
    )
    db.session.add(execucao)
    db.session.flush()

    if not alertas.empty:
        db.session.execute(
            insert(AlertaAnomalia),
            [
                {
                    "despesa_id": int(alerta.despesa_id),
                    "execucao_id": execucao.id,
                    "metodo": alerta.metodo,
                    "score": float(alerta.score),
                    "motivo": alerta.motivo,
                    "status_revisao": STATUS_PENDENTE,
                    "criado_em": iniciada_em,
                }
                for alerta in alertas.itertuples(index=False)
            ],
        )
    execucao.duracao_s = round(time.perf_counter() - inicio, 3)
    return execucao


def _travar_analise() -> None:
    """Impede duas análises ao mesmo tempo (botão e job, por exemplo) no PostgreSQL.

    Sem isso, as duas poderiam ver os mesmos pares (despesa, método) como novos e
    duplicar alertas. A trava vale até o fim da transação (commit ou rollback) e pode
    ser obtida de novo na mesma transação (o job a obtém antes de chamar a análise).
    """
    if db.session.get_bind().dialect.name == "postgresql":
        db.session.execute(text("SELECT pg_advisory_xact_lock(:chave)"), {"chave": CHAVE_TRAVA})


def _sem_alertas_existentes(alertas: pd.DataFrame) -> pd.DataFrame:
    """Remove os pares (despesa, método) que já têm alerta (decisão D3)."""
    if alertas.empty:
        return alertas
    existentes = set(
        db.session.execute(
            select(AlertaAnomalia.despesa_id, AlertaAnomalia.metodo).where(
                AlertaAnomalia.metodo.in_(alertas["metodo"].unique().tolist())
            )
        ).tuples()
    )
    if not existentes:
        return alertas
    novos = [
        (int(d), m) not in existentes
        for d, m in zip(alertas["despesa_id"], alertas["metodo"], strict=True)
    ]
    return alertas[novos].reset_index(drop=True)


def _parametros_registrados(parametros: dict, metodos: list[str]) -> dict:
    """O que fica em ``ExecucaoAnalise.parametros`` para reproduzir a execução (RNF06)."""
    return {
        "metodos": metodos,
        **{metodo: parametros.get(metodo, {}) for metodo in metodos},
        "dimensao_valor": DIMENSAO_DETECCAO,
        "n_minimo_grupo": N_MINIMO_GRUPO,
    }
