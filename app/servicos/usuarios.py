"""Serviço de usuários: criação com validação de perfil e e-mail único."""

from sqlalchemy import func, select

from app.extensoes import db
from app.models import Usuario
from app.models.dominio import PERFIS


class UsuarioInvalidoError(ValueError):
    """Dados de usuário inválidos (perfil desconhecido, e-mail repetido etc.)."""


def buscar_por_email(email: str) -> Usuario | None:
    email = email.strip().lower()
    return db.session.scalar(select(Usuario).where(func.lower(Usuario.email) == email))


def criar_usuario(nome: str, email: str, senha: str, perfil: str) -> Usuario:
    """Cria o usuário com a senha em hash. Não faz commit."""
    nome = (nome or "").strip()
    email = (email or "").strip().lower()
    if not nome:
        raise UsuarioInvalidoError("Informe o nome.")
    if "@" not in email:
        raise UsuarioInvalidoError("Informe um e-mail válido.")
    if len(senha or "") < 8:
        raise UsuarioInvalidoError("A senha deve ter pelo menos 8 caracteres.")
    if perfil not in PERFIS:
        raise UsuarioInvalidoError(f"Perfil inválido: {perfil}. Use um de: {', '.join(PERFIS)}.")
    if buscar_por_email(email) is not None:
        raise UsuarioInvalidoError(f"Já existe um usuário com o e-mail {email}.")

    usuario = Usuario(nome=nome, email=email, perfil=perfil, ativo=True)
    usuario.definir_senha(senha)
    db.session.add(usuario)
    return usuario
