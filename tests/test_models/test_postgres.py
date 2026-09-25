"""Testes que exigem PostgreSQL: migrations e trigger de imutabilidade do parecer.

São pulados se TEST_DATABASE_URL não estiver definida. No Docker Compose, o
banco ``despesas_teste`` é criado automaticamente (docker/postgres-init).
"""

import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest


def _motivo_para_pular() -> str | None:
    """Retorna o motivo para pular os testes, ou None se o PostgreSQL responde."""
    from dotenv import load_dotenv

    load_dotenv()
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        return "TEST_DATABASE_URL não definida"
    try:
        from sqlalchemy import create_engine

        motor = create_engine(url)
        with motor.connect():
            pass
        motor.dispose()
    except Exception as erro:  # noqa: BLE001
        return (
            f"PostgreSQL de teste indisponível ({type(erro).__name__}). "
            "Rode: docker compose up -d db"
        )
    return None


_MOTIVO = _motivo_para_pular()

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(_MOTIVO is not None, reason=_MOTIVO or ""),
]

PASTA_MIGRATIONS = str(Path(__file__).resolve().parents[2] / "migrations")


@pytest.fixture
def app_pg():
    from flask_migrate import downgrade, upgrade

    from app import create_app
    from app.config import TestPostgresConfig
    from app.extensoes import db

    app = create_app(TestPostgresConfig)
    with app.app_context():
        downgrade(directory=PASTA_MIGRATIONS, revision="base")  # garante banco limpo
        upgrade(directory=PASTA_MIGRATIONS)
        yield app
        db.session.remove()
        downgrade(directory=PASTA_MIGRATIONS, revision="base")


def test_migrations_refletem_modelos(app_pg):
    """Falha se alguém mudar um modelo e esquecer de gerar a migration."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.extensoes import db

    with db.engine.connect() as conexao:
        contexto = MigrationContext.configure(conexao, opts={"compare_type": True})
        diferencas = compare_metadata(contexto, db.metadata)
    assert diferencas == []


def _parecer_registrado():
    from app.extensoes import db
    from app.models import AlertaAnomalia, Despesa, ExecucaoAnalise, Parecer, Usuario

    usuario = Usuario(nome="Auditor", email="auditor@teste.com", perfil="auditor")
    usuario.definir_senha("senha-segura-123")
    despesa = Despesa(
        valor=Decimal("300.00"),
        data=date(2026, 9, 5),
        categoria="Hospedagem",
        conta_contabil="3.1.04",
        centro_custo="CC-01",
        funcionario="F002",
    )
    execucao = ExecucaoAnalise(parametros={}, seed=42)
    alerta = AlertaAnomalia(
        despesa=despesa, execucao=execucao, metodo="iqr", score=2.5, motivo="Acima de Q3 + 1,5·IQR"
    )
    db.session.add_all([usuario, despesa, execucao, alerta])
    db.session.flush()
    parecer = Parecer(
        alerta_id=alerta.id,
        usuario_id=usuario.id,
        status="necessita_justificativa",
        observacao="Solicitar comprovante.",
    )
    db.session.add(parecer)
    db.session.commit()
    return parecer


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE parecer SET observacao = 'alterado'",
        "DELETE FROM parecer",
        "TRUNCATE parecer CASCADE",
    ],
)
def test_trigger_bloqueia_alteracao_direta_no_banco(app_pg, sql):
    """Mesmo SQL direto, fora do ORM, não altera pareceres (RNF02)."""
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from app.extensoes import db
    from app.models import Parecer

    parecer = _parecer_registrado()
    with pytest.raises(DBAPIError, match="somente inserção"):
        db.session.execute(text(sql))
    db.session.rollback()
    assert db.session.get(Parecer, parecer.id).observacao == "Solicitar comprovante."


def test_valor_monetario_preservado_como_numeric(app_pg):
    from app.extensoes import db
    from app.models import Despesa

    db.session.add(
        Despesa(
            valor=Decimal("0.10") + Decimal("0.20"),
            data=date(2026, 9, 6),
            categoria="Combustível",
            conta_contabil="3.1.05",
            centro_custo="CC-02",
            funcionario="F003",
        )
    )
    db.session.commit()
    valor = db.session.query(Despesa.valor).scalar()
    assert valor == Decimal("0.30")


def test_analise_com_trava_no_postgres(app_pg):
    """Durante a análise, outra conexão não consegue a trava; no commit ela é liberada."""
    from sqlalchemy import text

    from app.extensoes import db
    from app.models import Despesa
    from app.servicos.analise import CHAVE_TRAVA, executar_analise

    db.session.add_all(
        Despesa(
            valor=Decimal("100.00"),
            data=date(2026, 3, 2),
            categoria="Viagens",
            conta_contabil="3.1.01",
            centro_custo="CC-ADM",
            funcionario="F001",
        )
        for _ in range(20)
    )
    db.session.commit()

    def trava_livre_em_outra_conexao():
        with db.engine.connect() as outra:
            livre = outra.execute(
                text("SELECT pg_try_advisory_xact_lock(:chave)"), {"chave": CHAVE_TRAVA}
            ).scalar()
            outra.rollback()
            return livre

    execucao = executar_analise(None)
    assert trava_livre_em_outra_conexao() is False  # análise em andamento segura a trava
    db.session.commit()

    assert execucao.total_despesas == 20
    assert trava_livre_em_outra_conexao() is True  # liberada no commit
