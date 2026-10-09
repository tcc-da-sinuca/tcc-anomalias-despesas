"""Lançamento de despesas com verificação na hora (aprovação prévia, item 34 de MUDANCAS).

Ao cadastrar ou importar despesas, os quatro métodos rodam contra o histórico de
despesas válidas, uma vez para todo o lote:

- nenhum alerta: a despesa entra como **válida**;
- algum alerta: entra como **pendente** e abre um pedido de aprovação (``SolicitacaoAprovacao``);
- algum alerta de gravidade **crítica** (``motor.gravidade``): entra como **rejeitada** e o
  pedido fica ``rejeitada_automaticamente``; pode ser encaminhado para decisão humana.

Os alertas ficam ligados a uma ``ExecucaoAnalise`` do tipo ``verificacao_lancamento``,
com parâmetros e seed (RNF06). A carga do histórico (base sintética) não passa por aqui
com verificação: ``verificar=False`` grava tudo como válido.

Não faz commit.
"""

import time
from dataclasses import dataclass, field

import pandas as pd
from sqlalchemy import insert

from app.extensoes import db
from app.models import (
    AlertaAnomalia,
    Despesa,
    EventoSolicitacao,
    ExecucaoAnalise,
    SolicitacaoAprovacao,
    Usuario,
)
from app.models.base import agora_utc
from app.models.dominio import (
    EVENTO_CRIADA,
    EVENTO_REJEITADA_AUTOMATICAMENTE,
    METODO_ISOLATION_FOREST,
    SITUACAO_PENDENTE,
    SITUACAO_REJEITADA,
    SITUACAO_VALIDA,
    SOLICITACAO_PENDENTE,
    SOLICITACAO_REJEITADA_AUTOMATICAMENTE,
    STATUS_PENDENTE,
)
from app.servicos.analise import carregar_despesas, parametros_registrados, travar_analise
from app.servicos.estatisticas import recalcular_estatisticas
from app.servicos.parametros import obter_parametros
from motor.consolidador import DETECTORES, consolidar, executar_detectores
from motor.gravidade import NIVEL_REJEICAO_AUTOMATICA, NOMES_NIVEIS, mais_grave

TIPO_VERIFICACAO = "verificacao_lancamento"


@dataclass
class ResultadoLancamento:
    """O que aconteceu com uma despesa lançada."""

    despesa: Despesa
    solicitacao: SolicitacaoAprovacao | None = None
    alertas: list[dict] = field(default_factory=list)

    @property
    def situacao(self) -> str:
        return self.despesa.situacao


def lancar_despesas(
    dados: list[dict], usuario: Usuario, lote_id: int | None = None, verificar: bool = True
) -> list[ResultadoLancamento]:
    """Grava as despesas (já validadas pela importação) conforme a verificação."""
    if not dados:
        return []
    if not verificar:
        despesas = [Despesa(**d, lote_id=lote_id, situacao=SITUACAO_VALIDA) for d in dados]
        db.session.add_all(despesas)
        db.session.flush()
        recalcular_estatisticas()
        return [ResultadoLancamento(d) for d in despesas]

    travar_analise()
    inicio = time.perf_counter()
    parametros = obter_parametros()
    metodos = list(DETECTORES)
    historico = carregar_despesas()
    novas = pd.DataFrame(
        {
            "despesa_id": [-(i + 1) for i in range(len(dados))],  # ids provisórios
            "valor": [float(d["valor"]) for d in dados],
            "data": pd.to_datetime([d["data"] for d in dados]),
            **{
                c: [d[c] for d in dados]
                for c in ("categoria", "conta_contabil", "centro_custo", "funcionario")
            },
        }
    )
    # Sem histórico, o DataFrame vazio não tem tipos definidos e o concat do pandas avisa.
    tudo = novas if historico.empty else pd.concat([historico, novas], ignore_index=True)
    alertas = consolidar(executar_detectores(tudo, parametros, metodos))
    alertas = alertas[alertas["despesa_id"] < 0]

    resultados = []
    for i, d in enumerate(dados):
        da_despesa = alertas[alertas["despesa_id"] == -(i + 1)].to_dict("records")
        gravidade = mais_grave(a["gravidade"] for a in da_despesa)
        if not da_despesa:
            situacao = SITUACAO_VALIDA
        elif gravidade == NIVEL_REJEICAO_AUTOMATICA:
            situacao = SITUACAO_REJEITADA
        else:
            situacao = SITUACAO_PENDENTE
        despesa = Despesa(**d, lote_id=lote_id, situacao=situacao)
        db.session.add(despesa)
        resultados.append(ResultadoLancamento(despesa, alertas=da_despesa))
    db.session.flush()

    com_alerta = [r for r in resultados if r.alertas]
    if com_alerta:
        execucao = ExecucaoAnalise(
            parametros={**parametros_registrados(parametros, metodos), "tipo": TIPO_VERIFICACAO},
            seed=int(parametros[METODO_ISOLATION_FOREST]["random_state"]),
            total_despesas=len(dados),
            total_alertas=sum(len(r.alertas) for r in com_alerta),
            executada_por=usuario.id,
        )
        db.session.add(execucao)
        db.session.flush()
        agora = agora_utc()
        db.session.execute(
            insert(AlertaAnomalia),
            [
                {
                    "despesa_id": r.despesa.id,
                    "execucao_id": execucao.id,
                    "metodo": a["metodo"],
                    "score": float(a["score"]),
                    "motivo": a["motivo"],
                    "excesso": float(a["excesso"]),
                    "gravidade": a["gravidade"],
                    "status_revisao": STATUS_PENDENTE,
                    "criado_em": agora,
                }
                for r in com_alerta
                for a in r.alertas
            ],
        )
        for r in com_alerta:
            r.solicitacao = _abrir_solicitacao(r, usuario)
        execucao.duracao_s = round(time.perf_counter() - inicio, 3)

    if any(r.situacao == SITUACAO_VALIDA for r in resultados):
        recalcular_estatisticas()
    return resultados


def _abrir_solicitacao(resultado: ResultadoLancamento, usuario: Usuario) -> SolicitacaoAprovacao:
    gravidade = mais_grave(a["gravidade"] for a in resultado.alertas)
    automatica = resultado.situacao == SITUACAO_REJEITADA
    solicitacao = SolicitacaoAprovacao(
        despesa_id=resultado.despesa.id,
        solicitada_por=usuario.id,
        status=SOLICITACAO_REJEITADA_AUTOMATICAMENTE if automatica else SOLICITACAO_PENDENTE,
        gravidade=gravidade,
    )
    db.session.add(solicitacao)
    db.session.flush()
    db.session.add(
        EventoSolicitacao(
            solicitacao_id=solicitacao.id,
            tipo=EVENTO_CRIADA,
            usuario_id=usuario.id,
            observacao=f"{len(resultado.alertas)} alerta(s) no lançamento.",
        )
    )
    if automatica:
        criticos = [
            a["metodo"] for a in resultado.alertas if a["gravidade"] == NIVEL_REJEICAO_AUTOMATICA
        ]
        db.session.add(
            EventoSolicitacao(
                solicitacao_id=solicitacao.id,
                tipo=EVENTO_REJEITADA_AUTOMATICAMENTE,
                usuario_id=None,
                observacao=(
                    f"Gravidade {NOMES_NIVEIS[NIVEL_REJEICAO_AUTOMATICA].lower()} em: "
                    f"{', '.join(sorted(set(criticos)))}. Pode ser encaminhado para aprovação."
                ),
            )
        )
    return solicitacao
