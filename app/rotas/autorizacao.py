"""Controle de acesso por perfil (RNF03)."""

from functools import wraps

from flask import abort
from flask_login import current_user

from app.extensoes import login_manager
from app.models.dominio import PERFIL_ADMINISTRADOR


def perfil_requerido(*perfis: str):
    """Restringe a rota aos perfis informados.

    O administrador sempre tem acesso, porque pode fazer tudo o que o auditor
    faz (seção 4 do CLAUDE.md). Usuário não autenticado é enviado ao login
    (ou recebe 401 na API); usuário sem o perfil recebe 403.

    Uso::

        @bp.route("/parametros")
        @perfil_requerido(PERFIL_ADMINISTRADOR)
        def parametros(): ...
    """

    def decorador(view):
        @wraps(view)
        def envolvida(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.perfil != PERFIL_ADMINISTRADOR and current_user.perfil not in perfis:
                abort(403)
            return view(*args, **kwargs)

        return envolvida

    return decorador
