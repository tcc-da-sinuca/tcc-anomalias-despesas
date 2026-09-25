"""Comandos de linha de comando (flask <comando>)."""

import os
from pathlib import Path

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

    @app.cli.command("seed-base")
    @click.option(
        "--arquivo",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        help="CSV gerado por dados/gerar_base_sintetica.py. Sem esta opção, a base é gerada agora.",
    )
    @click.option("--seed", default=42, show_default=True, help="Seed usada ao gerar a base.")
    @click.option("--forcar", is_flag=True, help="Substitui a base sintética já carregada.")
    def seed_base(arquivo, seed, forcar):
        """Carrega a base sintética de despesas, sem os rótulos de anomalia.

        Pode ser executado várias vezes: se a base já estiver carregada, não faz nada.
        """
        from sqlalchemy import select

        from app.models import Usuario
        from app.servicos.importacao import ArquivoInvalidoError
        from app.servicos.usuarios import buscar_por_email
        from dados.gerar_base_sintetica import NOME_BASE, ConfiguracaoBase, gerar_base, salvar_base
        from dados.seed_banco import CargaBaseError, buscar_lote, carregar_base

        nome_arquivo = arquivo.name if arquivo else f"{NOME_BASE}.csv"
        existente = buscar_lote(nome_arquivo)
        if existente is not None and not forcar:
            click.echo(
                f"Base sintética já carregada (lote {existente.id}). Use --forcar para substituir."
            )
            return

        email = os.environ.get("ADMIN_EMAIL")
        usuario = buscar_por_email(email) if email else None
        if usuario is None or not usuario.eh_administrador:
            usuario = db.session.scalar(
                select(Usuario).where(Usuario.perfil == PERFIL_ADMINISTRADOR).order_by(Usuario.id)
            )
        if usuario is None:
            raise click.ClickException("Nenhum administrador cadastrado. Rode: flask seed-admin")

        if arquivo is None:
            config = ConfiguracaoBase(seed=seed)
            arquivo = salvar_base(gerar_base(config), config)["csv"]
            click.echo(f"Base gerada em {arquivo} (seed {seed}).")

        try:
            lote = carregar_base(arquivo, usuario, forcar=forcar)
        except (CargaBaseError, ArquivoInvalidoError) as erro:
            db.session.rollback()
            raise click.ClickException(str(erro)) from erro
        db.session.commit()
        click.echo(
            f"{lote.linhas_validas} despesas carregadas no lote {lote.id}. "
            "Estatísticas de referência recalculadas."
        )

    @app.cli.command("recalcular-estatisticas")
    def recalcular_estatisticas_cmd():
        """Recalcula as estatísticas de referência de todas as despesas (US02)."""
        from app.servicos.estatisticas import recalcular_estatisticas

        grupos = recalcular_estatisticas()
        db.session.commit()
        click.echo(f"Estatísticas recalculadas: {grupos} grupos.")

    @app.cli.command("agendador")
    @click.option("--uma-vez", is_flag=True, help="Roda o job uma vez e termina (sem agendar).")
    def agendador(uma_vez):
        """Agenda o job de reprocessamento das despesas novas (container "agendador")."""
        import logging
        from datetime import datetime

        from apscheduler.schedulers.blocking import BlockingScheduler

        from app.servicos.reprocessamento import reprocessar

        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        log = logging.getLogger("agendador")

        def job():
            with app.app_context():
                try:
                    execucao = reprocessar()
                    db.session.commit()
                except Exception:  # noqa: BLE001 - registra e tenta de novo no próximo ciclo
                    db.session.rollback()
                    log.exception("Falha no reprocessamento; nova tentativa no próximo ciclo.")
                    return
                if execucao is None:
                    log.info("Sem despesas novas desde a última análise.")
                else:
                    log.info(
                        "Análise %s: %s despesas, %s alertas novos em %s s.",
                        execucao.id,
                        execucao.total_despesas,
                        execucao.total_alertas,
                        execucao.duracao_s,
                    )

        if uma_vez:
            job()
            return
        intervalo = app.config["REPROCESSAMENTO_INTERVALO_MIN"]
        if intervalo <= 0:
            click.echo("Reprocessamento desativado (REPROCESSAMENTO_INTERVALO_MIN=0).")
            return
        agendador_ = BlockingScheduler(timezone="UTC")
        agendador_.add_job(
            job,
            "interval",
            minutes=intervalo,
            next_run_time=datetime.now(),
            max_instances=1,
            coalesce=True,
            id="reprocessamento",
        )
        log.info("Reprocessamento a cada %s minuto(s).", intervalo)
        try:
            agendador_.start()
        except (KeyboardInterrupt, SystemExit):
            log.info("Agendador encerrado.")

    @app.cli.command("executar-analise")
    @click.option(
        "--metodo", "metodos", multiple=True, help="Método a executar (repetível). Padrão: todos."
    )
    @click.option(
        "--email", help="Usuário registrado como autor. Sem ele, conta como execução automática."
    )
    def executar_analise_cmd(metodos, email):
        """Executa a análise de anomalias sobre todas as despesas."""
        from app.servicos.analise import MetodoDesconhecidoError, executar_analise
        from app.servicos.usuarios import buscar_por_email

        usuario = None
        if email:
            usuario = buscar_por_email(email)
            if usuario is None:
                raise click.ClickException(f"Usuário {email} não encontrado.")
        try:
            execucao = executar_analise(usuario, metodos or None)
        except MetodoDesconhecidoError as erro:
            raise click.ClickException(str(erro)) from erro
        db.session.commit()
        click.echo(
            f"Análise {execucao.id}: {execucao.total_despesas} despesas, "
            f"{execucao.total_alertas} alertas novos em {execucao.duracao_s} s."
        )
