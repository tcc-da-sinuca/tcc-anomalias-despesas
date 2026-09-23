"""Aplicação Flask: detecção de anomalias em despesas corporativas."""

from flask import Flask, jsonify, render_template, request

from app.config import Config
from app.extensoes import csrf, db, login_manager, migrate


def create_app(config_class=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

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

    return app


def _configurar_login(app: Flask) -> None:
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Faça login para acessar o sistema."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def carregar_usuario(usuario_id: str):
        from app.models import Usuario

        return db.session.get(Usuario, int(usuario_id))

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
