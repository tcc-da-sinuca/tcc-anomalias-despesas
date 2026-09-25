"""Configurações da aplicação, lidas de variáveis de ambiente (.env)."""

import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "chave-de-desenvolvimento-insegura")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://tcc:tcc@localhost:5432/despesas"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Tamanho máximo de upload na importação de despesas (16 MB).
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True

    # Job de reprocessamento (container "agendador"): intervalo em minutos; 0 desliga.
    REPROCESSAMENTO_INTERVALO_MIN = int(os.environ.get("REPROCESSAMENTO_INTERVALO_MIN", "15"))


class TestConfig(Config):
    """Configuração dos testes: SQLite em memória, sem CSRF."""

    TESTING = True
    SECRET_KEY = "chave-de-teste"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False


class TestPostgresConfig(TestConfig):
    """Testes que dependem de recursos do PostgreSQL (trigger, migrations)."""

    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "")
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
