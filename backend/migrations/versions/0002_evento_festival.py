"""festival em eventos

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("eventos", sa.Column("festival", sa.Text))
    op.create_index(
        "ix_eventos_festival_trgm", "eventos", ["festival"],
        postgresql_using="gin", postgresql_ops={"festival": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_eventos_festival_trgm", table_name="eventos")
    op.drop_column("eventos", "festival")
