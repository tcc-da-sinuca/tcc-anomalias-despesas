"""Job de reprocessamento: analisa as despesas novas automaticamente (seção 2 do CLAUDE.md).

Roda no container ``agendador`` (comando ``flask agendador``), a cada
``REPROCESSAMENTO_INTERVALO_MIN`` minutos. Só executa a análise quando o número de
despesas mudou desde a última análise completa (todos os métodos); assim o
histórico não se enche de análises vazias. A execução fica sem autor
(``executada_por`` vazio), e a regra de não repetir alertas faz com que só as
novidades gerem alertas.
"""

from sqlalchemy import func, select

from app.extensoes import db
from app.models import Despesa, ExecucaoAnalise
from app.models.dominio import SITUACAO_VALIDA
from app.servicos.analise import executar_analise, travar_analise
from motor.consolidador import DETECTORES

# Quantas análises recentes olhar para achar a última completa.
_ANALISES_CONSULTADAS = 50


def ultima_analise_completa() -> ExecucaoAnalise | None:
    """A análise mais recente que rodou todos os métodos sobre a base (não as verificações
    feitas no lançamento, que avaliam só as despesas novas)."""
    recentes = db.session.scalars(
        select(ExecucaoAnalise)
        .order_by(ExecucaoAnalise.iniciada_em.desc(), ExecucaoAnalise.id.desc())
        .limit(_ANALISES_CONSULTADAS)
    )
    todos = set(DETECTORES)
    for execucao in recentes:
        parametros = execucao.parametros or {}
        if parametros.get("tipo") == "verificacao_lancamento":
            continue
        if set(parametros.get("metodos", [])) >= todos:
            return execucao
    return None


def ultima_analise_da_base() -> ExecucaoAnalise | None:
    """A análise mais recente sobre a base, de qualquer método (exclui as verificações
    feitas no lançamento). É a "última análise" do dashboard e do relatório."""
    for execucao in db.session.scalars(
        select(ExecucaoAnalise)
        .order_by(ExecucaoAnalise.iniciada_em.desc(), ExecucaoAnalise.id.desc())
        .limit(_ANALISES_CONSULTADAS)
    ):
        if (execucao.parametros or {}).get("tipo") != "verificacao_lancamento":
            return execucao
    return None


def ha_despesas_novas() -> bool:
    """Há despesas válidas e o total mudou desde a última análise completa (ou nunca houve uma)."""
    total = db.session.scalar(
        select(func.count(Despesa.id)).where(Despesa.situacao == SITUACAO_VALIDA)
    )
    if not total:
        return False
    ultima = ultima_analise_completa()
    return ultima is None or ultima.total_despesas != total


def reprocessar() -> ExecucaoAnalise | None:
    """Executa a análise se houver despesas novas; senão, devolve ``None``. Não faz commit.

    A verificação acontece depois de obter a trava de análise: se outra análise (o
    botão, por exemplo) estiver rodando, o job espera e decide com o resultado dela.
    Sem isso, o job decidia antes, esperava a trava e analisava de novo à toa.
    """
    travar_analise()
    if not ha_despesas_novas():
        return None
    return executar_analise(None)
