"""Entidades do domínio (seção 5 do CLAUDE.md).

Importar este pacote registra todos os modelos no metadata do SQLAlchemy.
"""

from app.models.analise import AlertaAnomalia, EstatisticaReferencia, ExecucaoAnalise
from app.models.despesa import Despesa, LoteImportacao
from app.models.revisao import ParametroMetodo, Parecer, ParecerImutavelError
from app.models.usuario import Usuario

__all__ = [
    "AlertaAnomalia",
    "Despesa",
    "EstatisticaReferencia",
    "ExecucaoAnalise",
    "LoteImportacao",
    "ParametroMetodo",
    "Parecer",
    "ParecerImutavelError",
    "Usuario",
]
