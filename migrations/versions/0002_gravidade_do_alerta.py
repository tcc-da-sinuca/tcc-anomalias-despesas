"""Gravidade do alerta

Acrescenta a AlertaAnomalia quanto o score passou do limite do método (excesso) e o
nível de gravidade correspondente (leve, moderada, alta ou critica; motor/gravidade.py).
As colunas são opcionais: alertas criados antes desta versão ficam sem gravidade.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("alerta_anomalia", schema=None) as batch_op:
        batch_op.add_column(sa.Column("excesso", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("gravidade", sa.String(length=10), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_alerta_anomalia_gravidade"), ["gravidade"], unique=False
        )
        batch_op.create_check_constraint(
            op.f("ck_alerta_anomalia_gravidade_valida"),
            "gravidade IS NULL OR gravidade IN ('leve', 'moderada', 'alta', 'critica')",
        )


def downgrade():
    with op.batch_alter_table("alerta_anomalia", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_alerta_anomalia_gravidade_valida"), type_="check")
        batch_op.drop_index(batch_op.f("ix_alerta_anomalia_gravidade"))
        batch_op.drop_column("gravidade")
        batch_op.drop_column("excesso")
