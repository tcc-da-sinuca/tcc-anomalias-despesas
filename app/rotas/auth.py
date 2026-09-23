"""Blueprint de autenticação: login e logout."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func, select

from app.extensoes import db
from app.models import Usuario

bp = Blueprint("auth", __name__)


def _destino_seguro(destino: str | None) -> str:
    """Aceita apenas caminhos internos, evitando redirecionamento para outro site."""
    if destino and destino.startswith("/") and not destino.startswith("//"):
        return destino
    return url_for("web.inicio")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("web.inicio"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        senha = request.form.get("senha") or ""
        usuario = db.session.scalar(select(Usuario).where(func.lower(Usuario.email) == email))

        # Mensagem única para não revelar se o e-mail existe.
        if usuario is None or not usuario.verificar_senha(senha) or not usuario.ativo:
            flash("E-mail ou senha inválidos.", "danger")
            return render_template("auth/login.html", email=email), 401

        login_user(usuario)
        return redirect(_destino_seguro(request.args.get("next")))

    return render_template("auth/login.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Sessão encerrada.", "info")
    return redirect(url_for("auth.login"))
