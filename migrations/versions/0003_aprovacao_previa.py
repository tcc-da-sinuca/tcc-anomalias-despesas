"""Aprovação prévia de despesas

Acrescenta a situação da despesa (valida, pendente ou rejeitada; as já existentes ficam
válidas), o pedido de aprovação de despesas lançadas fora do padrão e o histórico de
cada pedido, que é somente inserção (eventos do SQLAlchemy e trigger no PostgreSQL).
Item 34 de MUDANCAS_PARA_DOCUMENTACAO.md.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-08

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


SQL_FUNCAO_EVENTO_IMUTAVEL = """
CREATE OR REPLACE FUNCTION impedir_alteracao_evento_solicitacao() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Eventos de pedido são somente inserção: operação % não permitida', TG_OP
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;
"""

SQL_TRIGGER_LINHA = """
CREATE TRIGGER trg_evento_solicitacao_imutavel
    BEFORE UPDATE OR DELETE ON evento_solicitacao
    FOR EACH ROW EXECUTE FUNCTION impedir_alteracao_evento_solicitacao();
"""

SQL_TRIGGER_TRUNCATE = """
CREATE TRIGGER trg_evento_solicitacao_sem_truncate
    BEFORE TRUNCATE ON evento_solicitacao
    FOR EACH STATEMENT EXECUTE FUNCTION impedir_alteracao_evento_solicitacao();
"""


def upgrade():
    op.create_table(
        "solicitacao_aprovacao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("despesa_id", sa.Integer(), nullable=False),
        sa.Column("solicitada_por", sa.Integer(), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("gravidade", sa.String(length=10), nullable=True),
        sa.Column("prioritaria", sa.Boolean(), nullable=False),
        sa.Column("decidida_por", sa.Integer(), nullable=True),
        sa.Column("decidida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("justificativa", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "gravidade IS NULL OR gravidade IN ('leve', 'moderada', 'alta', 'critica')",
            name=op.f("ck_solicitacao_aprovacao_gravidade_valida"),
        ),
        sa.CheckConstraint(
            "status IN ('pendente', 'aprovada', 'rejeitada', 'rejeitada_automaticamente')",
            name=op.f("ck_solicitacao_aprovacao_status_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["decidida_por"],
            ["usuario.id"],
            name=op.f("fk_solicitacao_aprovacao_decidida_por_usuario"),
        ),
        sa.ForeignKeyConstraint(
            ["despesa_id"], ["despesa.id"], name=op.f("fk_solicitacao_aprovacao_despesa_id_despesa")
        ),
        sa.ForeignKeyConstraint(
            ["solicitada_por"],
            ["usuario.id"],
            name=op.f("fk_solicitacao_aprovacao_solicitada_por_usuario"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_solicitacao_aprovacao")),
    )
    with op.batch_alter_table("solicitacao_aprovacao", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_solicitacao_aprovacao_despesa_id"), ["despesa_id"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_solicitacao_aprovacao_status"), ["status"], unique=False
        )

    op.create_table(
        "evento_solicitacao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("solicitacao_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "tipo IN ('criada', 'rejeitada_automaticamente', 'encaminhada', "
            "'aprovada', 'rejeitada')",
            name=op.f("ck_evento_solicitacao_tipo_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["solicitacao_id"],
            ["solicitacao_aprovacao.id"],
            name=op.f("fk_evento_solicitacao_solicitacao_id_solicitacao_aprovacao"),
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuario.id"], name=op.f("fk_evento_solicitacao_usuario_id_usuario")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evento_solicitacao")),
    )
    with op.batch_alter_table("evento_solicitacao", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_evento_solicitacao_solicitacao_id"), ["solicitacao_id"], unique=False
        )

    with op.batch_alter_table("despesa", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("situacao", sa.String(length=10), server_default="valida", nullable=False)
        )
        batch_op.create_index(batch_op.f("ix_despesa_situacao"), ["situacao"], unique=False)
        batch_op.create_check_constraint(
            op.f("ck_despesa_situacao_valida"), "situacao IN ('valida', 'pendente', 'rejeitada')"
        )

    # Histórico dos pedidos imutável também no banco, como o parecer (RNF02).
    if op.get_bind().dialect.name == "postgresql":
        op.execute(SQL_FUNCAO_EVENTO_IMUTAVEL)
        op.execute(SQL_TRIGGER_LINHA)
        op.execute(SQL_TRIGGER_TRUNCATE)


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_evento_solicitacao_sem_truncate ON evento_solicitacao"
        )
        op.execute("DROP TRIGGER IF EXISTS trg_evento_solicitacao_imutavel ON evento_solicitacao")
        op.execute("DROP FUNCTION IF EXISTS impedir_alteracao_evento_solicitacao()")

    with op.batch_alter_table("despesa", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_despesa_situacao_valida"), type_="check")
        batch_op.drop_index(batch_op.f("ix_despesa_situacao"))
        batch_op.drop_column("situacao")

    with op.batch_alter_table("evento_solicitacao", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_evento_solicitacao_solicitacao_id"))

    op.drop_table("evento_solicitacao")
    with op.batch_alter_table("solicitacao_aprovacao", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_solicitacao_aprovacao_status"))
        batch_op.drop_index(batch_op.f("ix_solicitacao_aprovacao_despesa_id"))

    op.drop_table("solicitacao_aprovacao")
