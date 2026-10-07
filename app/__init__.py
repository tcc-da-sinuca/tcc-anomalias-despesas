"""Aplicação Flask: detecção de anomalias em despesas corporativas."""

from flask import Flask, jsonify, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import Config
from app.extensoes import csrf, db, login_manager, migrate

# Valores de exemplo que nunca podem chegar à produção.
CHAVES_INSEGURAS = {"troque-esta-chave", "chave-de-desenvolvimento-insegura", "chave-de-teste"}
TAMANHO_MINIMO_CHAVE = 32


class ConfiguracaoInseguraError(RuntimeError):
    """Configuração de produção com valores de exemplo ou fracos."""


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)
    if app.config.get("PRODUCAO"):
        _configurar_producao(app)

    db.init_app(app)
    migrate.init_app(app, db, compare_type=True)
    csrf.init_app(app)
    _configurar_login(app)

    # Importa os modelos para registrá-los no metadata (migrations e user_loader).
    from app import models  # noqa: F401
    from app.rotas.api import bp as api_bp
    from app.rotas.auth import bp as auth_bp
    from app.rotas.web import bp as web_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    from app.cli import registrar_comandos

    registrar_comandos(app)
    _registrar_erros(app)

    from app.filtros import registrar_filtros

    registrar_filtros(app)

    return app


def _configurar_producao(app: Flask) -> None:
    """Ajustes para rodar atrás do proxy HTTPS da VPS (docs/IMPLANTACAO.md)."""
    chave = app.config.get("SECRET_KEY") or ""
    if chave in CHAVES_INSEGURAS or len(chave) < TAMANHO_MINIMO_CHAVE:
        raise ConfiguracaoInseguraError(
            f"SECRET_KEY de exemplo ou curta demais (mínimo {TAMANHO_MINIMO_CHAVE} caracteres). "
            'Gere uma com: python3 -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    # O Nginx informa o esquema (https), o host e o IP do cliente nos cabeçalhos X-Forwarded-*.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config.update(
        SESSION_COOKIE_SECURE=True,
        REMEMBER_COOKIE_SECURE=True,
        PREFERRED_URL_SCHEME="https",
    )


def _configurar_login(app: Flask) -> None:
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Faça login para acessar o sistema."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def carregar_usuario(usuario_id: str):
        from app.models import Usuario

        usuario = db.session.get(Usuario, int(usuario_id))
        # Usuário desativado perde a sessão já aberta. O UserMixin do Flask-Login 0.6 já
        # trata inativo como não autenticado; a verificação aqui deixa a regra explícita.
        return usuario if usuario is not None and usuario.ativo else None

    @login_manager.unauthorized_handler
    def nao_autenticado():
        # A API responde JSON; as páginas redirecionam para o login.
        if request.blueprint == "api":
            return jsonify(erro="Autenticação necessária."), 401
        from flask import flash, redirect, url_for

        flash(login_manager.login_message, login_manager.login_message_category)
        destino = request.full_path if request.query_string else request.path
        return redirect(url_for(login_manager.login_view, next=destino))


def _registrar_erros(app: Flask) -> None:
    def _responder(codigo: int, mensagem: str):
        if request.blueprint == "api" or request.path.startswith("/api/"):
            return jsonify(erro=mensagem), codigo
        return render_template("erros/erro.html", codigo=codigo, mensagem=mensagem), codigo

    @app.errorhandler(403)
    def proibido(_erro):
        return _responder(403, "Seu perfil não tem permissão para acessar este recurso.")

    @app.errorhandler(404)
    def nao_encontrado(_erro):
        return _responder(404, "Página ou recurso não encontrado.")

    @app.errorhandler(413)
    def arquivo_grande(_erro):
        return _responder(413, "Arquivo grande demais. O limite é de 16 MB.")

    @app.errorhandler(500)
    def erro_interno(_erro):
        db.session.rollback()
        return _responder(500, "Erro interno. Tente de novo; se persistir, avise o administrador.")
