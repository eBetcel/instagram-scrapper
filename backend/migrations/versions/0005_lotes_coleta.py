"""lotes de coleta via Apify

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "lotes_coleta",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tipo", sa.String, nullable=False),
        sa.Column("horario", TS),
        sa.Column("janela", sa.Text, nullable=False),
        sa.Column("limite", sa.Integer, nullable=False),
        sa.Column("perfis", sa.ARRAY(sa.Text), nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="pendente"),
        sa.Column("run_ids", sa.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("posts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("posts_novos", sa.Integer, nullable=False, server_default="0"),
        sa.Column("custo_estimado", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("criado_em", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("concluido_em", TS),
        sa.Column("erro_msg", sa.Text),
        sa.CheckConstraint("tipo IN ('agendado', 'novos')", name="ck_lotes_coleta_tipo"),
        sa.CheckConstraint(
            "status IN ('pendente', 'executando', 'concluido', 'erro')",
            name="ck_lotes_coleta_status",
        ),
    )
    op.create_index(
        "uq_lotes_coleta_agendado_horario",
        "lotes_coleta",
        ["horario"],
        unique=True,
        postgresql_where=sa.text("tipo = 'agendado'"),
    )


def downgrade() -> None:
    op.drop_index("uq_lotes_coleta_agendado_horario", table_name="lotes_coleta")
    op.drop_table("lotes_coleta")
