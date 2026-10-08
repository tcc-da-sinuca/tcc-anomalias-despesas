"""Blueprint das páginas web (Jinja2)."""

from pathlib import Path

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user

from app.extensoes import db
from app.formularios import DespesaForm, ExecutarAnaliseForm, ImportacaoForm, ParecerForm
from app.models import ExecucaoAnalise, LoteImportacao, Usuario
from app.models.dominio import METODOS, PERFIL_ADMINISTRADOR, PERFIL_AUDITOR, PERFIS, STATUS_REVISAO
from app.repositorios import alertas as repo_alertas
from app.repositorios.despesas import paginar_despesas, paginar_lotes, valores_distintos
from app.rotas.autorizacao import perfil_requerido
from app.servicos import parametros as servico_parametros
from app.servicos import relatorio as servico_relatorio
from app.servicos import usuarios as servico_usuarios
from app.servicos.analise import executar_analise
from app.servicos.dashboard import resumo as resumo_dashboard
from app.servicos.estatisticas import listar_estatisticas, obter_estatistica
from app.servicos.importacao import (
    CAMPOS,
    CAMPOS_TEXTO,
    ArquivoInvalidoError,
    DespesaInvalidaError,
    cadastrar_despesa,
    importar_arquivo,
)
from app.servicos.revisao import ParecerInvalidoError, registrar_parecer

bp = Blueprint("web", __name__)

NOMES_DIMENSOES = {
    "categoria": "Categoria",
    "conta_contabil": "Conta contábil",
    "centro_custo": "Centro de custo",
}


@bp.route("/")
@perfil_requerido(PERFIL_AUDITOR)
def inicio():
    """Dashboard (US09)."""
    return render_template("web/inicio.html", resumo=resumo_dashboard())


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


ARQUIVO_EXEMPLO = (
    Path(__file__).resolve().parents[2] / "dados" / "exemplos" / "importacao_demonstracao.csv"
)


@bp.route("/despesas/importar/exemplo")
@perfil_requerido(PERFIL_AUDITOR)
def exemplo_importacao():
    """CSV de exemplo (formato do Excel brasileiro), o mesmo do roteiro de demonstração."""
    return send_file(
        ARQUIVO_EXEMPLO,
        mimetype="text/csv",
        as_attachment=True,
        download_name="exemplo_despesas.csv",
    )


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


@bp.route("/analises")
@perfil_requerido(PERFIL_AUDITOR)
def analises():
    pagina = repo_alertas.paginar_execucoes(request.args.get("pagina", 1, type=int))
    return render_template("web/analises.html", pagina=pagina, form=ExecutarAnaliseForm())


@bp.route("/analises", methods=["POST"])
@perfil_requerido(PERFIL_AUDITOR)
def executar():
    # O token CSRF do formulário é verificado pelo CSRFProtect antes de chegar aqui.
    execucao = executar_analise(current_user)
    db.session.commit()
    flash(
        f"Análise concluída: {execucao.total_despesas} despesa(s) analisada(s), "
        f"{execucao.total_alertas} alerta(s) novo(s).",
        "success",
    )
    return redirect(url_for("web.analise", execucao_id=execucao.id))


@bp.route("/analises/<int:execucao_id>")
@perfil_requerido(PERFIL_AUDITOR)
def analise(execucao_id: int):
    execucao = db.get_or_404(ExecucaoAnalise, execucao_id)
    return render_template(
        "web/analise.html",
        execucao=execucao,
        por_metodo=repo_alertas.alertas_por_metodo(execucao.id),
    )


@bp.route("/alertas")
@perfil_requerido(PERFIL_AUDITOR)
def alertas():
    """Lista de alertas com filtros combináveis (US06, US10)."""
    try:
        filtros = repo_alertas.FiltrosAlertas.de_parametros(request.args)
        erro_filtro = None
    except repo_alertas.FiltroInvalidoError as erro:
        filtros, erro_filtro = repo_alertas.FiltrosAlertas(), erro
    try:
        ordem = repo_alertas.ler_ordem(request.args.get("ordem"))
    except repo_alertas.FiltroInvalidoError:
        ordem = repo_alertas.ORDEM_PADRAO  # ordem desconhecida na URL: usa a padrão
    pagina = repo_alertas.paginar_alertas(
        request.args.get("pagina", 1, type=int), filtros=filtros, ordem=ordem
    )
    return render_template(
        "web/alertas.html",
        pagina=pagina,
        filtros=filtros,
        erro_filtro=erro_filtro,
        opcoes={campo: valores_distintos(campo) for campo in repo_alertas.CAMPOS_DESPESA},
        metodos=METODOS,
        status_revisao=STATUS_REVISAO,
        ordem=ordem,
        ordenacoes=repo_alertas.ORDENACOES,
        ordem_padrao=repo_alertas.ORDEM_PADRAO,
    ), (400 if erro_filtro else 200)


@bp.route("/alertas/<int:alerta_id>", methods=["GET", "POST"])
@perfil_requerido(PERFIL_AUDITOR)
def alerta(alerta_id: int):
    """Detalhe do alerta com o formulário de parecer (US07, US08)."""
    alerta = repo_alertas.obter_alerta(alerta_id)
    if alerta is None:
        abort(404)
    form = ParecerForm()
    if form.validate_on_submit():
        try:
            registrar_parecer(alerta, current_user, form.status.data, form.observacao.data)
        except ParecerInvalidoError as erro:
            db.session.rollback()
            getattr(form, erro.campo).errors.append(str(erro))
        else:
            db.session.commit()
            flash("Parecer registrado.", "success")
            return redirect(url_for("web.alerta", alerta_id=alerta.id))
    status = 400 if request.method == "POST" else 200
    return render_template(
        "web/alerta.html",
        alerta=alerta,
        outros=repo_alertas.outros_alertas_da_despesa(alerta),
        contexto=obter_estatistica("categoria", alerta.despesa.categoria),
        form=form,
    ), status


@bp.route("/parametros")
@perfil_requerido(PERFIL_AUDITOR)
def parametros():
    """Parâmetros dos métodos (US12): o auditor vê; o administrador altera."""
    return render_template(
        "web/parametros.html",
        itens=servico_parametros.listar_parametros(),
        pode_editar=current_user.perfil == PERFIL_ADMINISTRADOR,
        enviados={},
        erros={},
    )


@bp.route("/parametros", methods=["POST"])
@perfil_requerido(PERFIL_ADMINISTRADOR)
def salvar_parametros():
    # O token CSRF é verificado pelo CSRFProtect antes de chegar aqui.
    enviados = {r.nome: request.form.get(r.nome, "") for r in servico_parametros.REGRAS}
    alteracoes: dict[str, dict] = {}
    for regra in servico_parametros.REGRAS:
        alteracoes.setdefault(regra.metodo, {})[regra.chave] = enviados[regra.nome]
    try:
        alterados = servico_parametros.atualizar_parametros(alteracoes, current_user)
    except servico_parametros.ParametrosInvalidosError as erro:
        db.session.rollback()
        return render_template(
            "web/parametros.html",
            itens=servico_parametros.listar_parametros(),
            pode_editar=True,
            enviados=enviados,
            erros=erro.erros,
        ), 400
    db.session.commit()
    if alterados:
        flash(
            f"{len(alterados)} parâmetro(s) alterado(s). A mudança vale para as próximas análises.",
            "success",
        )
    else:
        flash("Nenhum parâmetro foi alterado.", "info")
    return redirect(url_for("web.parametros"))


@bp.route("/usuarios")
@perfil_requerido(PERFIL_ADMINISTRADOR)
def usuarios():
    """Gerenciamento de usuários (somente administrador)."""
    return render_template(
        "web/usuarios.html", usuarios=servico_usuarios.listar_usuarios(), perfis=PERFIS, novo={}
    )


@bp.route("/usuarios", methods=["POST"])
@perfil_requerido(PERFIL_ADMINISTRADOR)
def criar_usuario():
    novo = {campo: request.form.get(campo, "") for campo in ("nome", "email", "perfil")}
    try:
        usuario = servico_usuarios.criar_usuario(
            novo["nome"], novo["email"], request.form.get("senha", ""), novo["perfil"]
        )
    except servico_usuarios.UsuarioInvalidoError as erro:
        db.session.rollback()
        flash(str(erro), "danger")
        return render_template(
            "web/usuarios.html",
            usuarios=servico_usuarios.listar_usuarios(),
            perfis=PERFIS,
            novo=novo,
        ), 400
    db.session.commit()
    flash(f"Usuário {usuario.email} criado como {usuario.perfil}.", "success")
    return redirect(url_for("web.usuarios"))


@bp.route("/usuarios/<int:usuario_id>/perfil", methods=["POST"])
@perfil_requerido(PERFIL_ADMINISTRADOR)
def alterar_perfil_usuario(usuario_id: int):
    usuario = db.get_or_404(Usuario, usuario_id)
    try:
        servico_usuarios.alterar_perfil(usuario, request.form.get("perfil", ""), current_user)
    except servico_usuarios.UsuarioInvalidoError as erro:
        db.session.rollback()
        flash(str(erro), "danger")
    else:
        db.session.commit()
        flash(f"Perfil de {usuario.email}: {usuario.perfil}.", "success")
    return redirect(url_for("web.usuarios"))


@bp.route("/usuarios/<int:usuario_id>/ativo", methods=["POST"])
@perfil_requerido(PERFIL_ADMINISTRADOR)
def alterar_ativo_usuario(usuario_id: int):
    usuario = db.get_or_404(Usuario, usuario_id)
    ativo = request.form.get("ativo") == "1"
    try:
        servico_usuarios.definir_ativo(usuario, ativo, current_user)
    except servico_usuarios.UsuarioInvalidoError as erro:
        db.session.rollback()
        flash(str(erro), "danger")
    else:
        db.session.commit()
        flash(f"Usuário {usuario.email} {'reativado' if ativo else 'desativado'}.", "success")
    return redirect(url_for("web.usuarios"))


@bp.route("/relatorios")
@perfil_requerido(PERFIL_AUDITOR)
def relatorios():
    """Relatório mensal (US11). Sem ano e mês, mostra o mês da despesa mais recente."""
    ano, mes = request.args.get("ano"), request.args.get("mes")
    if not ano and not mes:
        ano, mes = servico_relatorio.mes_mais_recente()
    try:
        relatorio = servico_relatorio.relatorio_mensal(ano, mes)
        erro = None
    except servico_relatorio.PeriodoInvalidoError as falha:
        relatorio, erro = None, str(falha)
    return render_template(
        "web/relatorio.html",
        relatorio=relatorio,
        erro=erro,
        meses=servico_relatorio.NOMES_MESES,
        ano_escolhido=ano,
        mes_escolhido=mes,
    ), (400 if erro else 200)
