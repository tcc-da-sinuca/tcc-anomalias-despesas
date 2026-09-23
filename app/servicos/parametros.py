"""Serviço de parâmetros dos métodos de detecção (RF13).

Nesta etapa só garante que os parâmetros padrão existam. A leitura tipada, a
validação e a edição pelo administrador (US12) entram na Sprint 4.
"""

from app.extensoes import db
from app.models import ParametroMetodo
from app.models.dominio import PARAMETROS_PADRAO


def garantir_parametros_padrao() -> int:
    """Insere os parâmetros padrão que ainda não existem. Retorna quantos inseriu.

    Não sobrescreve valores já configurados. Não faz commit.
    """
    inseridos = 0
    for metodo, parametros in PARAMETROS_PADRAO.items():
        for chave, valor in parametros.items():
            if db.session.get(ParametroMetodo, (metodo, chave)) is None:
                db.session.add(ParametroMetodo(metodo=metodo, chave=chave, valor=valor))
                inseridos += 1
    return inseridos
