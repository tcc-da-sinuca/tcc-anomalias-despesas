"""Carrega a base sintética no banco como um lote de importação.

Só os campos da ``Despesa`` vão para o banco. O ``id_sintetico`` e os rótulos
(``anomalia_real``, ``tipo_anomalia``, ``grupo_anomalia``) ficam apenas no
arquivo gerado, que é o que o experimento usa.

Uso: ``flask seed-base`` (ver app/cli.py). Quando o serviço de importação da
US01 existir, a carga passa a usá-lo.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, func, insert, select

from app.extensoes import db
from app.models import AlertaAnomalia, Despesa, LoteImportacao, Usuario
from dados.gerar_base_sintetica import COLUNAS_DESPESA


class CargaBaseError(Exception):
    """A base não pôde ser carregada (arquivo inválido, lote com alertas etc.)."""


def ler_csv(caminho: Path) -> pd.DataFrame:
    """Lê o CSV gerado, convertendo valor para Decimal e data para date."""
    base = pd.read_csv(caminho, dtype=str, keep_default_na=False)
    faltando = [c for c in COLUNAS_DESPESA if c not in base.columns]
    if faltando:
        raise CargaBaseError(f"Colunas ausentes em {caminho.name}: {', '.join(faltando)}.")
    base["valor"] = base["valor"].map(Decimal)
    base["data"] = base["data"].map(date.fromisoformat)
    return base


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


def carregar_base(
    base: pd.DataFrame, nome_arquivo: str, importado_por: Usuario, forcar: bool = False
) -> LoteImportacao | None:
    """Insere as despesas num novo lote. Não faz commit.

    Se já existir um lote com o mesmo nome de arquivo, não carrega nada e
    retorna None, a menos que ``forcar`` seja verdadeiro: nesse caso o lote
    anterior e suas despesas são substituídos.
    """
    existente = buscar_lote(nome_arquivo)
    if existente is not None:
        if not forcar:
            return None
        _remover_lote(existente)

    lote = LoteImportacao(
        nome_arquivo=nome_arquivo,
        importado_por=importado_por.id,
        total_linhas=len(base),
        linhas_validas=len(base),
        erros=[],
    )
    db.session.add(lote)
    db.session.flush()

    registros = [
        {**{c: linha[c] for c in COLUNAS_DESPESA}, "lote_id": lote.id}
        for linha in base.to_dict("records")
    ]
    for registro in registros:
        registro["descricao"] = registro["descricao"] or None
    db.session.execute(insert(Despesa), registros)
    return lote
