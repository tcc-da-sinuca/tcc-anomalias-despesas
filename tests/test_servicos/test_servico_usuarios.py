"""Gerenciamento de usuários: perfil, ativação e proteções."""

import pytest


def test_listar_ativos_primeiro(sessao, auditor, administrador, usuario_inativo):
    from app.servicos.usuarios import listar_usuarios

    assert [u.email for u in listar_usuarios()][-1] == usuario_inativo.email


def test_alterar_perfil(sessao, auditor, administrador):
    from app.servicos.usuarios import alterar_perfil

    alterar_perfil(auditor, "administrador", administrador)
    assert auditor.perfil == "administrador"


def test_perfil_invalido(sessao, auditor, administrador):
    from app.servicos.usuarios import UsuarioInvalidoError, alterar_perfil

    with pytest.raises(UsuarioInvalidoError, match="Perfil inválido"):
        alterar_perfil(auditor, "gestor", administrador)


def test_nao_altera_o_proprio_perfil(sessao, auditor, administrador):
    from app.servicos.usuarios import UsuarioInvalidoError, alterar_perfil

    alterar_perfil(auditor, "administrador", administrador)  # agora há dois administradores
    with pytest.raises(UsuarioInvalidoError, match="seu próprio perfil"):
        alterar_perfil(administrador, "auditor", administrador)


def test_mantem_ao_menos_um_administrador_ativo(sessao, auditor, administrador):
    from app.servicos.usuarios import UsuarioInvalidoError, alterar_perfil, definir_ativo

    # o auditor não pode, mas o serviço também protege: responsável aqui é outro usuário
    with pytest.raises(UsuarioInvalidoError, match="pelo menos um administrador"):
        alterar_perfil(administrador, "auditor", auditor)
    with pytest.raises(UsuarioInvalidoError, match="pelo menos um administrador"):
        definir_ativo(administrador, False, auditor)


def test_desativar_e_reativar(sessao, auditor, administrador):
    from app.servicos.usuarios import definir_ativo

    definir_ativo(auditor, False, administrador)
    assert not auditor.ativo
    definir_ativo(auditor, True, administrador)
    assert auditor.ativo


def test_nao_desativa_a_si_mesmo(sessao, auditor, administrador):
    from app.servicos.usuarios import UsuarioInvalidoError, alterar_perfil, definir_ativo

    alterar_perfil(auditor, "administrador", administrador)
    with pytest.raises(UsuarioInvalidoError, match="a si mesmo"):
        definir_ativo(administrador, False, administrador)
