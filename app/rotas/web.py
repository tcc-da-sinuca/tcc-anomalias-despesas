"""Blueprint das páginas web (Jinja2).

Nesta etapa há só a página inicial. Importação, alertas, revisão e dashboard
entram nas próximas sprints.
"""

from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import func, select

from app.extensoes import db
from app.models import AlertaAnomalia, Despesa, LoteImportacao

bp = Blueprint("web", __name__)


@bp.route("/")
@login_required
def inicio():
    totais = {
        "despesas": db.session.scalar(select(func.count(Despesa.id))),
        "lotes": db.session.scalar(select(func.count(LoteImportacao.id))),
        "alertas": db.session.scalar(select(func.count(AlertaAnomalia.id))),
    }
    return render_template("web/inicio.html", totais=totais)
