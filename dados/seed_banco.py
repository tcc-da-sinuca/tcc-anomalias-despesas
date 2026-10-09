"""Carrega a base sintética no banco pelo serviço de importação (US01).

O CSV passa pelas mesmas validações de um arquivo enviado pelo auditor. As
colunas que não pertencem à ``Despesa`` (``id_sintetico`` e os rótulos
``anomalia_real``, ``tipo_anomalia``, ``grupo_anomalia``) são ignoradas pela
importação: elas existem só no arquivo, que é o que o experimento usa.

Uso: ``flask seed-base`` (ver app/cli.py).
"""

from pathlib import Path

from sqlalchemy import delete, func, select

from app.extensoes import db
from app.models import AlertaAnomalia, Despesa, LoteImportacao, Usuario
from app.servicos.estatisticas import recalcular_estatisticas
from app.servicos.importacao import importar_arquivo


class CargaBaseError(Exception):
    """A base não pôde ser carregada (lote com alertas, linhas inválidas etc.)."""


def buscar_lote(nome_arquivo: str) -> LoteImportacao | None:
    return db.session.scalar(
        select(LoteImportacao).where(LoteImportacao.nome_arquivo == nome_arquivo)
    )


def _remover_lote(lote: LoteImportacao) -> None:
    com_alerta = db.session.scalar(
        select(func.count(AlertaAnomalia.id))
        .join(Despesa, AlertaAnomalia.despesa_id == Despesa.id)
        .where(Despesa.lote_id == lote.id)
    )
    if com_alerta:
        raise CargaBaseError(
            f"O lote {lote.id} já tem {com_alerta} alertas e não pode ser substituído. "
            "Para recomeçar do zero, apague o banco (docker compose down -v)."
        )
    db.session.execute(delete(Despesa).where(Despesa.lote_id == lote.id))
    db.session.delete(lote)
    db.session.flush()
    recalcular_estatisticas()


def carregar_base(
    caminho_csv: Path, importado_por: Usuario, forcar: bool = False
) -> LoteImportacao | None:
    """Importa o CSV num novo lote. Não faz commit.

    Se já existir um lote com o mesmo nome de arquivo, não carrega nada e
    retorna None, a menos que ``forcar`` seja verdadeiro: nesse caso o lote
    anterior e suas despesas são substituídos. Qualquer linha recusada pela
    importação é tratada como erro, porque a base gerada deve ser sempre válida.
    """
    existente = buscar_lote(caminho_csv.name)
    if existente is not None:
        if not forcar:
            return None
        _remover_lote(existente)

    # Histórico de referência: entra direto como válido, sem verificação no lançamento.
    lote = importar_arquivo(
        caminho_csv.name, caminho_csv.read_bytes(), importado_por, verificar=False
    )
    if lote.erros:
        primeiro = lote.erros[0]
        raise CargaBaseError(
            f"{len(lote.erros)} erro(s) ao importar a base. "
            f"Primeiro: linha {primeiro['linha']}, {primeiro['mensagem']}."
        )
    return lote
