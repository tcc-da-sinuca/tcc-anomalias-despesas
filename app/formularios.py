"""Formulários web (Flask-WTF), usados principalmente pela proteção CSRF.

A validação dos dados de despesa fica no serviço de importação, para que o
cadastro manual e a importação sigam exatamente as mesmas regras.
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import StringField, TextAreaField


class ImportacaoForm(FlaskForm):
    arquivo = FileField(
        "Arquivo (CSV ou XLSX)",
        validators=[
            FileRequired("Selecione um arquivo."),
            FileAllowed(["csv", "xlsx"], "Envie um arquivo .csv ou .xlsx."),
        ],
    )


class ExecutarAnaliseForm(FlaskForm):
    """Só o botão "Executar análise"; o formulário existe pela proteção CSRF."""


class DespesaForm(FlaskForm):
    valor = StringField("Valor (R$)", render_kw={"inputmode": "decimal", "placeholder": "0,00"})
    data = StringField("Data", render_kw={"type": "date"})
    categoria = StringField("Categoria", render_kw={"list": "sugestoes-categoria"})
    conta_contabil = StringField("Conta contábil", render_kw={"list": "sugestoes-conta_contabil"})
    centro_custo = StringField("Centro de custo", render_kw={"list": "sugestoes-centro_custo"})
    funcionario = StringField("Funcionário", render_kw={"list": "sugestoes-funcionario"})
    descricao = TextAreaField("Descrição (opcional)", render_kw={"rows": 2})
