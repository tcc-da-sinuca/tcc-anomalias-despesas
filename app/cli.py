"""Comandos de linha de comando (flask <comando>)."""

import os

import click
from flask import Flask

from app.extensoes import db
from app.models.dominio import PERFIL_ADMINISTRADOR, PERFIS


def registrar_comandos(app: Flask) -> None:
    @app.cli.command("seed-admin")
    def seed_admin():
        """Cria o administrador inicial a partir do .env (ADMIN_*) e os parâmetros padrão.

        Pode ser executado várias vezes: não duplica nada.
        """
        from app.servicos.parametros import garantir_parametros_padrao
        from app.servicos.usuarios import buscar_por_email, criar_usuario

        email = os.environ.get("ADMIN_EMAIL")
        senha = os.environ.get("ADMIN_SENHA")
        nome = os.environ.get("ADMIN_NOME", "Administrador")
        if not email or not senha:
            raise click.ClickException("Defina ADMIN_EMAIL e ADMIN_SENHA no .env.")

        if buscar_por_email(email) is None:
            criar_usuario(nome, email, senha, PERFIL_ADMINISTRADOR)
            click.echo(f"Administrador {email} criado.")
        else:
            click.echo(f"Administrador {email} já existe.")

        inseridos = garantir_parametros_padrao()
        db.session.commit()
        click.echo(f"Parâmetros padrão inseridos: {inseridos}.")

    @app.cli.command("criar-usuario")
    @click.option("--nome", prompt=True)
    @click.option("--email", prompt=True)
    @click.option("--perfil", type=click.Choice(PERFIS), default="auditor", show_default=True)
    @click.password_option("--senha")
    def criar_usuario_cmd(nome, email, perfil, senha):
        """Cria um usuário (auditor ou administrador)."""
        from app.servicos.usuarios import UsuarioInvalidoError, criar_usuario

        try:
            criar_usuario(nome, email, senha, perfil)
        except UsuarioInvalidoError as erro:
            raise click.ClickException(str(erro)) from erro
        db.session.commit()
        click.echo(f"Usuário {email} ({perfil}) criado.")
