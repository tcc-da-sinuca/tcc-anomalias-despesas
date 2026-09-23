"""Usuário do sistema (auditor ou administrador)."""

from flask_login import UserMixin
from sqlalchemy import Boolean, CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensoes import db
from app.models.dominio import PERFIL_ADMINISTRADOR, PERFIL_AUDITOR, SQL_PERFIS


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuario"
    __table_args__ = (CheckConstraint(f"perfil IN {SQL_PERFIS}", name="perfil_valido"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    perfil: Mapped[str] = mapped_column(String(20), nullable=False, default=PERFIL_AUDITOR)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def definir_senha(self, senha: str) -> None:
        """Armazena somente o hash da senha, nunca o texto puro (RNF03)."""
        self.senha_hash = generate_password_hash(senha)

    def verificar_senha(self, senha: str) -> bool:
        return check_password_hash(self.senha_hash, senha)

    @property
    def is_active(self) -> bool:  # usado pelo Flask-Login: usuário inativo não entra
        return bool(self.ativo)

    @property
    def eh_administrador(self) -> bool:
        return self.perfil == PERFIL_ADMINISTRADOR

    def __repr__(self) -> str:
        return f"<Usuario {self.email} ({self.perfil})>"
