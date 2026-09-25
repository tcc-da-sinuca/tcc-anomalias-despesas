"""Serviço de usuários: criação, troca de perfil e ativação (seção 4 do CLAUDE.md).

Usuários não são excluídos: os pareceres guardam quem os registrou (RNF02). Para
tirar o acesso de alguém, desative o usuário. O sistema sempre mantém pelo menos
um administrador ativo, e o administrador não pode desativar a si mesmo nem tirar
o próprio perfil de administrador.
"""

from sqlalchemy import func, select

from app.extensoes import db
from app.models import Usuario
from app.models.dominio import PERFIL_ADMINISTRADOR, PERFIS


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


def listar_usuarios() -> list[Usuario]:
    """Ativos primeiro, depois por nome."""
    return list(db.session.scalars(select(Usuario).order_by(Usuario.ativo.desc(), Usuario.nome)))


def _administradores_ativos() -> int:
    return db.session.scalar(
        select(func.count(Usuario.id)).where(
            Usuario.perfil == PERFIL_ADMINISTRADOR, Usuario.ativo.is_(True)
        )
    )


def _deixaria_sem_administrador(usuario: Usuario) -> bool:
    return (
        usuario.perfil == PERFIL_ADMINISTRADOR and usuario.ativo and _administradores_ativos() <= 1
    )


def alterar_perfil(usuario: Usuario, perfil: str, responsavel: Usuario) -> None:
    """Troca o perfil. Não faz commit."""
    if perfil not in PERFIS:
        raise UsuarioInvalidoError(f"Perfil inválido: {perfil}. Use um de: {', '.join(PERFIS)}.")
    if perfil == usuario.perfil:
        return
    if usuario.id == responsavel.id:
        raise UsuarioInvalidoError("Você não pode alterar o seu próprio perfil.")
    if _deixaria_sem_administrador(usuario):
        raise UsuarioInvalidoError("O sistema precisa de pelo menos um administrador ativo.")
    usuario.perfil = perfil


def definir_ativo(usuario: Usuario, ativo: bool, responsavel: Usuario) -> None:
    """Ativa ou desativa. Um usuário desativado perde o acesso na hora. Não faz commit."""
    if ativo == usuario.ativo:
        return
    if not ativo:
        if usuario.id == responsavel.id:
            raise UsuarioInvalidoError("Você não pode desativar a si mesmo.")
        if _deixaria_sem_administrador(usuario):
            raise UsuarioInvalidoError("O sistema precisa de pelo menos um administrador ativo.")
    usuario.ativo = ativo
