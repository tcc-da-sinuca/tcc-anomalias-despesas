"""Blueprint das páginas web (Jinja2)."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select

from app.extensoes import db
from app.formularios import DespesaForm, ImportacaoForm
from app.models import AlertaAnomalia, Despesa, LoteImportacao
from app.models.dominio import PERFIL_AUDITOR
from app.repositorios.despesas import paginar_despesas, paginar_lotes, valores_distintos
from app.rotas.autorizacao import perfil_requerido
from app.servicos.estatisticas import listar_estatisticas
from app.servicos.importacao import (
    CAMPOS,
    CAMPOS_TEXTO,
    ArquivoInvalidoError,
    DespesaInvalidaError,
    cadastrar_despesa,
    importar_arquivo,
)

bp = Blueprint("web", __name__)

NOMES_DIMENSOES = {
    "categoria": "Categoria",
    "conta_contabil": "Conta contábil",
    "centro_custo": "Centro de custo",
}


@bp.route("/")
@login_required
def inicio():
    totais = {
        "despesas": db.session.scalar(select(func.count(Despesa.id))),
        "lotes": db.session.scalar(select(func.count(LoteImportacao.id))),
        "alertas": db.session.scalar(select(func.count(AlertaAnomalia.id))),
    }
    return render_template("web/inicio.html", totais=totais)


@bp.route("/despesas")
@perfil_requerido(PERFIL_AUDITOR)
def despesas():
    lote_id = request.args.get("lote_id", type=int)
    pagina = paginar_despesas(request.args.get("pagina", 1, type=int), lote_id=lote_id)
    lote = db.session.get(LoteImportacao, lote_id) if lote_id else None
    return render_template("web/despesas.html", pagina=pagina, lote=lote)


@bp.route("/despesas/nova", methods=["GET", "POST"])
@perfil_requerido(PERFIL_AUDITOR)
def nova_despesa():
    form = DespesaForm()
    if form.validate_on_submit():
        try:
            cadastrar_despesa({campo: getattr(form, campo).data for campo in CAMPOS})
        except DespesaInvalidaError as erro:
            db.session.rollback()
            for campo, mensagem in erro.erros:
                getattr(form, campo).errors.append(mensagem)
        else:
            db.session.commit()
            flash(
                "Despesa cadastrada. As estatísticas de referência foram recalculadas.", "success"
            )
            return redirect(url_for("web.despesas"))
    sugestoes = {campo: valores_distintos(campo) for campo in CAMPOS_TEXTO}
    status = 400 if request.method == "POST" else 200
    return render_template("web/despesa_form.html", form=form, sugestoes=sugestoes), status


@bp.route("/despesas/importar", methods=["GET", "POST"])
@perfil_requerido(PERFIL_AUDITOR)
def importar():
    form = ImportacaoForm()
    if form.validate_on_submit():
        arquivo = form.arquivo.data
        try:
            lote = importar_arquivo(arquivo.filename, arquivo.read(), current_user)
        except ArquivoInvalidoError as erro:
            db.session.rollback()
            flash(str(erro), "danger")
        else:
            db.session.commit()
            return redirect(url_for("web.lote", lote_id=lote.id))
    status = 400 if request.method == "POST" else 200
    lotes = paginar_lotes(por_pagina=10).items
    return render_template("web/importar.html", form=form, lotes=lotes), status


@bp.route("/lotes/<int:lote_id>")
@perfil_requerido(PERFIL_AUDITOR)
def lote(lote_id: int):
    return render_template("web/lote.html", lote=db.get_or_404(LoteImportacao, lote_id))


@bp.route("/estatisticas")
@perfil_requerido(PERFIL_AUDITOR)
def estatisticas():
    return render_template(
        "web/estatisticas.html",
        por_dimensao=listar_estatisticas(),
        nomes_dimensoes=NOMES_DIMENSOES,
    )
