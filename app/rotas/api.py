"""Blueprint da API REST (prefixo /api).

Os endpoints da seção 6 do CLAUDE.md entram aqui ao longo das sprints.
Por enquanto há só a verificação de saúde (usada pelo Docker) e o usuário atual.
"""

from flask import Blueprint, jsonify
from flask_login import current_user, login_required
from sqlalchemy import text

from app.extensoes import csrf, db

bp = Blueprint("api", __name__)
# A API usa sessão + JSON. A proteção CSRF de formulários HTML não se aplica aqui;
# chamadas de escrita feitas pelo front-end devem enviar o cabeçalho X-CSRFToken.
csrf.exempt(bp)


@bp.route("/saude")
def saude():
    """Verifica se a aplicação responde e se o banco está acessível."""
    try:
        db.session.execute(text("SELECT 1"))
        banco = "ok"
    except Exception:  # noqa: BLE001 - qualquer falha de conexão conta como indisponível
        db.session.rollback()
        banco = "indisponivel"
    codigo = 200 if banco == "ok" else 503
    return jsonify(status="ok" if banco == "ok" else "erro", banco=banco), codigo


@bp.route("/usuario-atual")
@login_required
def usuario_atual():
    return jsonify(
        id=current_user.id,
        nome=current_user.nome,
        email=current_user.email,
        perfil=current_user.perfil,
    )
