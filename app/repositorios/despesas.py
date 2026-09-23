"""Consultas de despesas e lotes de importação."""

from sqlalchemy import select

from app.extensoes import db
from app.models import Despesa, LoteImportacao

POR_PAGINA_PADRAO = 50
POR_PAGINA_MAXIMO = 200


def paginar_despesas(pagina: int = 1, por_pagina: int = POR_PAGINA_PADRAO, lote_id=None):
    """Despesas da mais recente para a mais antiga. Retorna um ``Pagination``."""
    por_pagina = max(1, min(por_pagina, POR_PAGINA_MAXIMO))
    consulta = select(Despesa).order_by(Despesa.data.desc(), Despesa.id.desc())
    if lote_id is not None:
        consulta = consulta.where(Despesa.lote_id == lote_id)
    return db.paginate(consulta, page=max(pagina, 1), per_page=por_pagina, error_out=False)


def paginar_lotes(pagina: int = 1, por_pagina: int = 20):
    consulta = select(LoteImportacao).order_by(LoteImportacao.importado_em.desc())
    return db.paginate(consulta, page=max(pagina, 1), per_page=por_pagina, error_out=False)


def valores_distintos(campo: str, limite: int = 200) -> list[str]:
    """Valores já usados num campo (ex.: categorias), para sugerir no formulário."""
    coluna = getattr(Despesa, campo)
    return list(db.session.scalars(select(coluna).distinct().order_by(coluna).limit(limite)))
