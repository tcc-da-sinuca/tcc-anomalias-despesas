"""Blueprint da API REST (prefixo /api).

Os endpoints da seção 6 do CLAUDE.md entram aqui ao longo das sprints.
"""

from flask import Blueprint, Response, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import text

from app.extensoes import csrf, db
from app.models import ExecucaoAnalise
from app.models.dominio import PERFIL_ADMINISTRADOR, PERFIL_AUDITOR
from app.repositorios import alertas as repo_alertas
from app.repositorios.despesas import POR_PAGINA_PADRAO, paginar_despesas
from app.rotas.autorizacao import perfil_requerido
from app.servicos import parametros as servico_parametros
from app.servicos import relatorio as servico_relatorio
from app.servicos import solicitacoes as servico_solicitacoes
from app.servicos.analise import MetodoDesconhecidoError, executar_analise
from app.servicos.dashboard import resumo as resumo_dashboard
from app.servicos.importacao import ArquivoInvalidoError, importar_arquivo
from app.servicos.revisao import ParecerInvalidoError, registrar_parecer

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
        # Resultado da verificação no lançamento (aprovação prévia).
        "situacoes": {
            situacao: sum(1 for d in lote.despesas if d.situacao == situacao)
            for situacao in ("valida", "pendente", "rejeitada")
        },
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
    return jsonify(_pagina_json(pagina, _despesa_json))


def _pagina_json(pagina, serializar) -> dict:
    return {
        "itens": [serializar(item) for item in pagina.items],
        "pagina": pagina.page,
        "por_pagina": pagina.per_page,
        "total": pagina.total,
        "paginas": pagina.pages,
    }


def _execucao_json(execucao) -> dict:
    return {
        "id": execucao.id,
        "iniciada_em": execucao.iniciada_em.isoformat(),
        "duracao_s": execucao.duracao_s,
        "parametros": execucao.parametros,
        "seed": execucao.seed,
        "total_despesas": execucao.total_despesas,
        "total_alertas": execucao.total_alertas,
        "executada_por": execucao.executada_por,
        "alertas_por_metodo": repo_alertas.alertas_por_metodo(execucao.id),
    }


def _alerta_json(alerta) -> dict:
    return {
        "id": alerta.id,
        "despesa_id": alerta.despesa_id,
        "execucao_id": alerta.execucao_id,
        "metodo": alerta.metodo,
        "score": alerta.score,
        "motivo": alerta.motivo,
        "status_revisao": alerta.status_revisao,
        "criado_em": alerta.criado_em.isoformat(),
    }


def _parecer_json(parecer) -> dict:
    return {
        "id": parecer.id,
        "usuario_id": parecer.usuario_id,
        "status": parecer.status,
        "observacao": parecer.observacao,
        "criado_em": parecer.criado_em.isoformat(),
    }


@bp.route("/analises", methods=["POST"])
@perfil_requerido(PERFIL_AUDITOR)
def criar_analise():
    """Executa a análise sobre todas as despesas. Corpo opcional: ``{"metodos": ["zscore"]}``."""
    corpo = request.get_json(silent=True) or {}
    metodos = corpo.get("metodos")
    if metodos is not None and (
        not isinstance(metodos, list) or not all(isinstance(m, str) for m in metodos)
    ):
        return jsonify(erro="'metodos' deve ser uma lista de nomes de métodos."), 400
    try:
        execucao = executar_analise(current_user, metodos)
    except MetodoDesconhecidoError as erro:
        db.session.rollback()
        return jsonify(erro=str(erro)), 400
    db.session.commit()
    return jsonify(_execucao_json(execucao)), 201


@bp.route("/analises/<int:execucao_id>")
@perfil_requerido(PERFIL_AUDITOR)
def obter_analise(execucao_id: int):
    return jsonify(_execucao_json(db.get_or_404(ExecucaoAnalise, execucao_id)))


@bp.route("/alertas")
@perfil_requerido(PERFIL_AUDITOR)
def listar_alertas():
    """Lista paginada com filtros combináveis (US10).

    ``?data_inicio=2026-03-01&data_fim=2026-03-31&categoria=Viagens&conta_contabil=3.1.01``
    ``&centro_custo=CC-ADM&funcionario=F001&status=pendente&metodo=zscore&execucao_id=3``
    ``&pagina=1&por_pagina=50&ordem=valor_desc``. O período se refere à data da despesa.
    ``ordem``: padrao, data_desc, data_asc, valor_desc ou valor_asc.
    """
    try:
        filtros = repo_alertas.FiltrosAlertas.de_parametros(request.args)
        ordem = repo_alertas.ler_ordem(request.args.get("ordem"))
    except repo_alertas.FiltroInvalidoError as erro:
        return jsonify(erro=str(erro), campo=erro.campo), 400
    pagina = repo_alertas.paginar_alertas(
        request.args.get("pagina", 1, type=int),
        request.args.get("por_pagina", repo_alertas.POR_PAGINA_PADRAO, type=int),
        filtros,
        ordem,
    )
    return jsonify(
        _pagina_json(pagina, lambda a: {**_alerta_json(a), "despesa": _despesa_json(a.despesa)})
    )


@bp.route("/alertas/<int:alerta_id>")
@perfil_requerido(PERFIL_AUDITOR)
def obter_alerta(alerta_id: int):
    alerta = repo_alertas.obter_alerta(alerta_id)
    if alerta is None:
        return jsonify(erro="Alerta não encontrado."), 404
    return jsonify(
        {
            **_alerta_json(alerta),
            "despesa": _despesa_json(alerta.despesa),
            "pareceres": [_parecer_json(p) for p in alerta.pareceres],
        }
    )


@bp.route("/alertas/<int:alerta_id>/parecer", methods=["POST"])
@perfil_requerido(PERFIL_AUDITOR)
def criar_parecer(alerta_id: int):
    """Registra um parecer (US07, US08). Corpo: ``{"status": "irregular", "observacao": "..."}``."""
    alerta = repo_alertas.obter_alerta(alerta_id)
    if alerta is None:
        return jsonify(erro="Alerta não encontrado."), 404
    corpo = request.get_json(silent=True) or {}
    status, observacao = corpo.get("status"), corpo.get("observacao")
    if observacao is not None and not isinstance(observacao, str):
        return jsonify(erro="'observacao' deve ser texto.", campo="observacao"), 400
    try:
        parecer = registrar_parecer(alerta, current_user, status, observacao)
    except ParecerInvalidoError as erro:
        db.session.rollback()
        return jsonify(erro=str(erro), campo=erro.campo), 400
    db.session.commit()
    return jsonify({**_parecer_json(parecer), "status_revisao": alerta.status_revisao}), 201


@bp.route("/dashboard")
@perfil_requerido(PERFIL_AUDITOR)
def dashboard():
    """Indicadores do dashboard (US09). Valores monetários como texto, sem perder centavos."""
    resumo = resumo_dashboard()
    ultima = resumo["ultima_analise"]
    return jsonify(
        {
            **resumo,
            "valor_despesas": str(resumo["valor_despesas"]),
            "valor_sinalizado": str(resumo["valor_sinalizado"]),
            "ultima_analise": _execucao_json(ultima) if ultima else None,
        }
    )


def _parametros_json() -> list[dict]:
    return [
        {
            "metodo": item["regra"].metodo,
            "chave": item["regra"].chave,
            "valor": item["valor"],
            "padrao": item["padrao"],
            "tipo": item["regra"].tipo.__name__,
            "minimo": item["regra"].minimo,
            "maximo": item["regra"].maximo,
            "minimo_exclusivo": item["regra"].minimo_exclusivo,
            "rotulo": item["regra"].rotulo,
            "ajuda": item["regra"].ajuda,
            "alterado_por": item["alterado_por"].id if item["alterado_por"] else None,
            "alterado_em": item["alterado_em"].isoformat() if item["alterado_por"] else None,
        }
        for item in servico_parametros.listar_parametros()
    ]


@bp.route("/parametros")
@perfil_requerido(PERFIL_AUDITOR)
def listar_parametros():
    """Parâmetros atuais dos métodos, com faixa válida e padrão (US12). Leitura para todos."""
    return jsonify(parametros=_parametros_json())


@bp.route("/parametros", methods=["PUT"])
@perfil_requerido(PERFIL_ADMINISTRADOR)
def atualizar_parametros():
    """Altera parâmetros (somente administrador). Corpo: ``{"zscore": {"limiar": 2.5}}``.

    Tudo ou nada: se algum valor for inválido, nada muda e a resposta traz os erros.
    """
    try:
        alterados = servico_parametros.atualizar_parametros(
            request.get_json(silent=True), current_user
        )
    except servico_parametros.ParametrosInvalidosError as erro:
        db.session.rollback()
        return jsonify(erros=erro.erros), 400
    db.session.commit()
    return jsonify(alterados=alterados, parametros=_parametros_json())


@bp.route("/relatorios/mensal")
@perfil_requerido(PERFIL_AUDITOR)
def relatorio_mensal():
    """Relatório mensal (US11): ``?ano=2026&mes=3&formato=json|csv|pdf`` (padrão json).

    O mês se refere à data da despesa. O CSV segue o padrão do Excel brasileiro
    (``;`` e vírgula decimal), em UTF-8 com BOM para os acentos abrirem corretamente.
    """
    formato = (request.args.get("formato") or "json").lower()
    if formato not in ("json", "csv", "pdf"):
        return jsonify(erro="formato inválido. Use json, csv ou pdf.", campo="formato"), 400
    try:
        relatorio = servico_relatorio.relatorio_mensal(
            request.args.get("ano"), request.args.get("mes")
        )
    except servico_relatorio.PeriodoInvalidoError as erro:
        return jsonify(erro=str(erro)), 400

    if formato == "pdf":
        nome = f"relatorio_{relatorio['ano']}_{relatorio['mes']:02d}.pdf"
        return Response(
            servico_relatorio.para_pdf(relatorio),
            mimetype="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'},
        )
    if formato == "csv":
        nome = f"relatorio_{relatorio['ano']}_{relatorio['mes']:02d}.csv"
        return Response(
            "\ufeff" + servico_relatorio.para_csv(relatorio),
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'},
        )
    ultima = relatorio["ultima_analise"]
    return jsonify(
        {
            **relatorio,
            "inicio": relatorio["inicio"].isoformat(),
            "fim": relatorio["fim"].isoformat(),
            "valor_despesas": str(relatorio["valor_despesas"]),
            "valor_sinalizado": str(relatorio["valor_sinalizado"]),
            "ultima_analise": _execucao_json(ultima) if ultima else None,
        }
    )


def _solicitacao_json(s, detalhado: bool = False) -> dict:
    dados = {
        "id": s.id,
        "status": s.status,
        "prioritaria": s.prioritaria,
        "gravidade": s.gravidade,
        "solicitada_por": s.solicitada_por,
        "criada_em": s.criada_em.isoformat(),
        "decidida_por": s.decidida_por,
        "decidida_em": s.decidida_em.isoformat() if s.decidida_em else None,
        "justificativa": s.justificativa,
        "despesa": {**_despesa_json(s.despesa), "situacao": s.despesa.situacao},
    }
    if detalhado:
        dados["alertas"] = [
            {**_alerta_json(a), "excesso": a.excesso, "gravidade": a.gravidade}
            for a in s.despesa.alertas
        ]
        dados["eventos"] = [
            {
                "tipo": e.tipo,
                "usuario_id": e.usuario_id,
                "observacao": e.observacao,
                "criado_em": e.criado_em.isoformat(),
            }
            for e in s.eventos
        ]
    return dados


@bp.route("/solicitacoes")
@perfil_requerido(PERFIL_AUDITOR)
def listar_solicitacoes():
    """Pedidos de aprovação, do mais urgente para o menos: ``?status=pendente&pagina=1``."""
    try:
        pagina = servico_solicitacoes.paginar(
            request.args.get("status") or None, request.args.get("pagina", 1, type=int)
        )
    except servico_solicitacoes.SolicitacaoInvalidaError as erro:
        return jsonify(erro=str(erro), campo="status"), 400
    return jsonify(_pagina_json(pagina, _solicitacao_json))


@bp.route("/solicitacoes/<int:solicitacao_id>")
@perfil_requerido(PERFIL_AUDITOR)
def obter_solicitacao(solicitacao_id: int):
    solicitacao = servico_solicitacoes.obter(solicitacao_id)
    if solicitacao is None:
        return jsonify(erro="Pedido não encontrado."), 404
    return jsonify(_solicitacao_json(solicitacao, detalhado=True))


def _acao_em_solicitacao(solicitacao_id: int, acao, campo: str):
    solicitacao = servico_solicitacoes.obter(solicitacao_id)
    if solicitacao is None:
        return jsonify(erro="Pedido não encontrado."), 404
    corpo = request.get_json(silent=True) or {}
    try:
        acao(solicitacao, current_user, corpo.get(campo))
    except servico_solicitacoes.SolicitacaoInvalidaError as erro:
        db.session.rollback()
        return jsonify(erro=str(erro)), 400
    db.session.commit()
    return jsonify(_solicitacao_json(solicitacao, detalhado=True))


@bp.route("/solicitacoes/<int:solicitacao_id>/aprovar", methods=["POST"])
@perfil_requerido(PERFIL_ADMINISTRADOR)
def aprovar_solicitacao(solicitacao_id: int):
    """Corpo opcional: ``{"observacao": "..."}``."""
    return _acao_em_solicitacao(solicitacao_id, servico_solicitacoes.aprovar, "observacao")


@bp.route("/solicitacoes/<int:solicitacao_id>/rejeitar", methods=["POST"])
@perfil_requerido(PERFIL_ADMINISTRADOR)
def rejeitar_solicitacao(solicitacao_id: int):
    """Corpo: ``{"justificativa": "..."}`` (obrigatória)."""
    return _acao_em_solicitacao(solicitacao_id, servico_solicitacoes.rejeitar, "justificativa")


@bp.route("/solicitacoes/<int:solicitacao_id>/encaminhar", methods=["POST"])
@perfil_requerido(PERFIL_AUDITOR)
def encaminhar_solicitacao(solicitacao_id: int):
    """Corpo: ``{"justificativa": "..."}`` (obrigatória). Só pedidos rejeitados automaticamente."""
    return _acao_em_solicitacao(solicitacao_id, servico_solicitacoes.encaminhar, "justificativa")
