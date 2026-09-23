"""Serviço de parâmetros dos métodos de detecção (RF13).

Garante os parâmetros padrão e os lê já convertidos em número para o motor. A
validação e a edição pelo administrador (US12) entram na Sprint 4.
"""

from sqlalchemy import select

from app.extensoes import db
from app.models import ParametroMetodo
from app.models.dominio import PARAMETROS_PADRAO

# Parâmetros inteiros; os demais são float.
PARAMETROS_INTEIROS = {("isolation_forest", "random_state")}


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


def obter_parametros() -> dict[str, dict[str, float | int]]:
    """Parâmetros de cada método, como números: ``{"zscore": {"limiar": 3.0}, ...}``.

    Parte dos padrões e aplica os valores gravados em ``ParametroMetodo``.
    """
    textos = {metodo: dict(parametros) for metodo, parametros in PARAMETROS_PADRAO.items()}
    for parametro in db.session.scalars(select(ParametroMetodo)):
        textos.setdefault(parametro.metodo, {})[parametro.chave] = parametro.valor
    return {
        metodo: {chave: _converter(metodo, chave, valor) for chave, valor in parametros.items()}
        for metodo, parametros in textos.items()
    }


def _converter(metodo: str, chave: str, valor: str) -> float | int:
    return int(valor) if (metodo, chave) in PARAMETROS_INTEIROS else float(valor)
