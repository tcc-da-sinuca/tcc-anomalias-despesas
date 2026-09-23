"""Fixtures compartilhadas.

Por padrão os testes usam SQLite em memória (rápido, sem dependências). Os
testes marcados com ``postgres`` usam TEST_DATABASE_URL e ficam em
``tests/test_models/test_postgres.py``.

Os imports da aplicação ficam dentro das fixtures para que testes puros (motor,
domínio) rodem mesmo sem as dependências web instaladas.
"""

from datetime import date
from decimal import Decimal

import pytest

SENHA_TESTE = "senha-segura-123"


@pytest.fixture
def app():
    from app import create_app
    from app.config import TestConfig
    from app.extensoes import db

    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def sessao(app):
    from app.extensoes import db

    return db.session


@pytest.fixture
def client(app):
    return app.test_client()


def _criar_usuario(sessao, email, perfil, ativo=True):
    from app.models import Usuario

    usuario = Usuario(nome=email.split("@")[0].title(), email=email, perfil=perfil, ativo=ativo)
    usuario.definir_senha(SENHA_TESTE)
    sessao.add(usuario)
    sessao.commit()
    return usuario


@pytest.fixture
def auditor(sessao):
    return _criar_usuario(sessao, "auditor@teste.com", "auditor")


@pytest.fixture
def administrador(sessao):
    return _criar_usuario(sessao, "admin@teste.com", "administrador")


@pytest.fixture
def usuario_inativo(sessao):
    return _criar_usuario(sessao, "inativo@teste.com", "auditor", ativo=False)


@pytest.fixture
def entrar(client):
    """Faz login pelo formulário: entrar(usuario)."""

    def _entrar(usuario, senha=SENHA_TESTE):
        return client.post("/login", data={"email": usuario.email, "senha": senha})

    return _entrar


@pytest.fixture
def alerta(sessao, auditor):
    """Cadeia mínima: lote → despesa → execução → alerta."""
    from app.models import AlertaAnomalia, Despesa, ExecucaoAnalise, LoteImportacao

    lote = LoteImportacao(
        nome_arquivo="despesas.csv", importado_por=auditor.id, total_linhas=1, linhas_validas=1
    )
    despesa = Despesa(
        valor=Decimal("1520.75"),
        data=date(2026, 9, 12),
        categoria="Viagens",
        conta_contabil="3.1.01",
        centro_custo="CC-01",
        funcionario="F001",
        descricao="Passagem aérea",
        lote=lote,
    )
    execucao = ExecucaoAnalise(
        parametros={"zscore": {"limiar": 3}}, seed=42, executada_por=auditor.id
    )
    alerta = AlertaAnomalia(
        despesa=despesa,
        execucao=execucao,
        metodo="zscore",
        score=4.2,
        motivo="Valor 4,2x acima da média da categoria Viagens",
    )
    sessao.add_all([lote, despesa, execucao, alerta])
    sessao.commit()
    return alerta
