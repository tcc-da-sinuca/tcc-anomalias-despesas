"""Modelo de dados inicial e imutabilidade do parecer

Cria as 8 entidades da seção 5 do CLAUDE.md e o trigger do PostgreSQL que
impede UPDATE, DELETE e TRUNCATE na tabela parecer (RNF02).

Revision ID: 0001
Revises:
Create Date: 2026-09-22

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


SQL_FUNCAO_PARECER_IMUTAVEL = """
CREATE OR REPLACE FUNCTION impedir_alteracao_parecer() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Pareceres são somente inserção (RNF02): operação % não permitida', TG_OP
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;
"""

SQL_TRIGGER_LINHA = """
CREATE TRIGGER trg_parecer_imutavel
    BEFORE UPDATE OR DELETE ON parecer
    FOR EACH ROW EXECUTE FUNCTION impedir_alteracao_parecer();
"""

SQL_TRIGGER_TRUNCATE = """
CREATE TRIGGER trg_parecer_sem_truncate
    BEFORE TRUNCATE ON parecer
    FOR EACH STATEMENT EXECUTE FUNCTION impedir_alteracao_parecer();
"""


def upgrade():
    op.create_table(
        "usuario",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("senha_hash", sa.String(length=255), nullable=False),
        sa.Column("perfil", sa.String(length=20), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "perfil IN ('auditor', 'administrador')", name=op.f("ck_usuario_perfil_valido")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usuario")),
    )
    op.create_index(op.f("ix_usuario_email"), "usuario", ["email"], unique=True)

    op.create_table(
        "lote_importacao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome_arquivo", sa.String(length=255), nullable=False),
        sa.Column("importado_por", sa.Integer(), nullable=False),
        sa.Column("importado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_linhas", sa.Integer(), nullable=False),
        sa.Column("linhas_validas", sa.Integer(), nullable=False),
        sa.Column("erros", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["importado_por"], ["usuario.id"], name=op.f("fk_lote_importacao_importado_por_usuario")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lote_importacao")),
    )

    op.create_table(
        "despesa",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("valor", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("categoria", sa.String(length=100), nullable=False),
        sa.Column("conta_contabil", sa.String(length=50), nullable=False),
        sa.Column("centro_custo", sa.String(length=50), nullable=False),
        sa.Column("funcionario", sa.String(length=120), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("lote_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["lote_id"], ["lote_importacao.id"], name=op.f("fk_despesa_lote_id_lote_importacao")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_despesa")),
    )
    op.create_index(op.f("ix_despesa_data"), "despesa", ["data"], unique=False)
    op.create_index(op.f("ix_despesa_categoria"), "despesa", ["categoria"], unique=False)
    op.create_index(op.f("ix_despesa_conta_contabil"), "despesa", ["conta_contabil"], unique=False)
    op.create_index(op.f("ix_despesa_centro_custo"), "despesa", ["centro_custo"], unique=False)
    op.create_index(op.f("ix_despesa_funcionario"), "despesa", ["funcionario"], unique=False)
    op.create_index(op.f("ix_despesa_lote_id"), "despesa", ["lote_id"], unique=False)

    op.create_table(
        "estatistica_referencia",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dimensao", sa.String(length=100), nullable=False),
        sa.Column("chave", sa.String(length=255), nullable=False),
        sa.Column("media", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("desvio", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("q1", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("q3", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("calculada_em", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_estatistica_referencia")),
        sa.UniqueConstraint("dimensao", "chave", name=op.f("uq_estatistica_referencia_dimensao")),
    )

    op.create_table(
        "execucao_analise",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("iniciada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duracao_s", sa.Float(), nullable=True),
        sa.Column("parametros", sa.JSON(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("total_despesas", sa.Integer(), nullable=False),
        sa.Column("total_alertas", sa.Integer(), nullable=False),
        sa.Column("executada_por", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["executada_por"],
            ["usuario.id"],
            name=op.f("fk_execucao_analise_executada_por_usuario"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_execucao_analise")),
    )

    op.create_table(
        "alerta_anomalia",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("despesa_id", sa.Integer(), nullable=False),
        sa.Column("execucao_id", sa.Integer(), nullable=False),
        sa.Column("metodo", sa.String(length=20), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("status_revisao", sa.String(length=30), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "metodo IN ('zscore', 'iqr', 'isolation_forest', 'contextual')",
            name=op.f("ck_alerta_anomalia_metodo_valido"),
        ),
        sa.CheckConstraint(
            "status_revisao IN ('pendente', 'aprovado', 'irregular', 'necessita_justificativa')",
            name=op.f("ck_alerta_anomalia_status_revisao_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["despesa_id"], ["despesa.id"], name=op.f("fk_alerta_anomalia_despesa_id_despesa")
        ),
        sa.ForeignKeyConstraint(
            ["execucao_id"],
            ["execucao_analise.id"],
            name=op.f("fk_alerta_anomalia_execucao_id_execucao_analise"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerta_anomalia")),
    )
    op.create_index(
        op.f("ix_alerta_anomalia_despesa_id"), "alerta_anomalia", ["despesa_id"], unique=False
    )
    op.create_index(
        op.f("ix_alerta_anomalia_execucao_id"), "alerta_anomalia", ["execucao_id"], unique=False
    )
    op.create_index(op.f("ix_alerta_anomalia_metodo"), "alerta_anomalia", ["metodo"], unique=False)
    op.create_index(
        op.f("ix_alerta_anomalia_status_revisao"),
        "alerta_anomalia",
        ["status_revisao"],
        unique=False,
    )

    op.create_table(
        "parecer",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alerta_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('aprovado', 'irregular', 'necessita_justificativa')",
            name=op.f("ck_parecer_status_valido"),
        ),
        sa.CheckConstraint(
            "status NOT IN ('irregular', 'necessita_justificativa') "
            "OR (observacao IS NOT NULL AND length(trim(observacao)) > 0)",
            name=op.f("ck_parecer_observacao_obrigatoria"),
        ),
        sa.ForeignKeyConstraint(
            ["alerta_id"], ["alerta_anomalia.id"], name=op.f("fk_parecer_alerta_id_alerta_anomalia")
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuario.id"], name=op.f("fk_parecer_usuario_id_usuario")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_parecer")),
    )
    op.create_index(op.f("ix_parecer_alerta_id"), "parecer", ["alerta_id"], unique=False)

    op.create_table(
        "parametro_metodo",
        sa.Column("metodo", sa.String(length=20), nullable=False),
        sa.Column("chave", sa.String(length=50), nullable=False),
        sa.Column("valor", sa.String(length=100), nullable=False),
        sa.Column("alterado_por", sa.Integer(), nullable=True),
        sa.Column("alterado_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "metodo IN ('zscore', 'iqr', 'isolation_forest', 'contextual')",
            name=op.f("ck_parametro_metodo_metodo_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["alterado_por"], ["usuario.id"], name=op.f("fk_parametro_metodo_alterado_por_usuario")
        ),
        sa.PrimaryKeyConstraint("metodo", "chave", name=op.f("pk_parametro_metodo")),
    )

    # RNF02: pareceres imutáveis também no banco (vale para qualquer cliente SQL).
    if op.get_bind().dialect.name == "postgresql":
        op.execute(SQL_FUNCAO_PARECER_IMUTAVEL)
        op.execute(SQL_TRIGGER_LINHA)
        op.execute(SQL_TRIGGER_TRUNCATE)


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_parecer_sem_truncate ON parecer")
        op.execute("DROP TRIGGER IF EXISTS trg_parecer_imutavel ON parecer")
        op.execute("DROP FUNCTION IF EXISTS impedir_alteracao_parecer()")

    op.drop_table("parametro_metodo")
    op.drop_index(op.f("ix_parecer_alerta_id"), table_name="parecer")
    op.drop_table("parecer")
    op.drop_index(op.f("ix_alerta_anomalia_status_revisao"), table_name="alerta_anomalia")
    op.drop_index(op.f("ix_alerta_anomalia_metodo"), table_name="alerta_anomalia")
    op.drop_index(op.f("ix_alerta_anomalia_execucao_id"), table_name="alerta_anomalia")
    op.drop_index(op.f("ix_alerta_anomalia_despesa_id"), table_name="alerta_anomalia")
    op.drop_table("alerta_anomalia")
    op.drop_table("execucao_analise")
    op.drop_table("estatistica_referencia")
    op.drop_index(op.f("ix_despesa_lote_id"), table_name="despesa")
    op.drop_index(op.f("ix_despesa_funcionario"), table_name="despesa")
    op.drop_index(op.f("ix_despesa_centro_custo"), table_name="despesa")
    op.drop_index(op.f("ix_despesa_conta_contabil"), table_name="despesa")
    op.drop_index(op.f("ix_despesa_categoria"), table_name="despesa")
    op.drop_index(op.f("ix_despesa_data"), table_name="despesa")
    op.drop_table("despesa")
    op.drop_table("lote_importacao")
    op.drop_index(op.f("ix_usuario_email"), table_name="usuario")
    op.drop_table("usuario")
