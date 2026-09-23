"""Blueprint da API REST (prefixo /api).

Os endpoints da seção 6 do CLAUDE.md entram aqui ao longo das sprints.
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import text

from app.extensoes import csrf, db
from app.models.dominio import PERFIL_AUDITOR
from app.repositorios.despesas import POR_PAGINA_PADRAO, paginar_despesas
from app.rotas.autorizacao import perfil_requerido
from app.servicos.importacao import ArquivoInvalidoError, importar_arquivo

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


def _despesa_json(despesa) -> dict:
    return {
        "id": despesa.id,
        "valor": str(despesa.valor),  # texto, para não perder centavos
        "data": despesa.data.isoformat(),
        "categoria": despesa.categoria,
        "conta_contabil": despesa.conta_contabil,
        "centro_custo": despesa.centro_custo,
        "funcionario": despesa.funcionario,
        "descricao": despesa.descricao,
        "lote_id": despesa.lote_id,
    }


def _lote_json(lote) -> dict:
    return {
        "id": lote.id,
        "nome_arquivo": lote.nome_arquivo,
        "importado_em": lote.importado_em.isoformat(),
        "total_linhas": lote.total_linhas,
        "linhas_validas": lote.linhas_validas,
        "erros": lote.erros,
    }


@bp.route("/despesas/importar", methods=["POST"])
@perfil_requerido(PERFIL_AUDITOR)
def importar_despesas():
    """Importa um CSV/XLSX enviado no campo ``arquivo`` (US01)."""
    arquivo = request.files.get("arquivo")
    if arquivo is None or not arquivo.filename:
        return jsonify(erro="Envie o arquivo no campo 'arquivo'."), 400
    try:
        lote = importar_arquivo(arquivo.filename, arquivo.read(), current_user)
    except ArquivoInvalidoError as erro:
        db.session.rollback()
        return jsonify(erro=str(erro)), 400
    db.session.commit()
    return jsonify(_lote_json(lote)), 201


@bp.route("/despesas")
@perfil_requerido(PERFIL_AUDITOR)
def listar_despesas():
    """Lista paginada: ``?pagina=1&por_pagina=50&lote_id=3``."""
    pagina = paginar_despesas(
        pagina=request.args.get("pagina", 1, type=int),
        por_pagina=request.args.get("por_pagina", POR_PAGINA_PADRAO, type=int),
        lote_id=request.args.get("lote_id", type=int),
    )
    return jsonify(
        itens=[_despesa_json(d) for d in pagina.items],
        pagina=pagina.page,
        por_pagina=pagina.per_page,
        total=pagina.total,
        paginas=pagina.pages,
    )
