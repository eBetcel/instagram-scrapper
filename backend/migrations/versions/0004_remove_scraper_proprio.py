"""remove o scraper próprio (contas de coleta, próxima coleta, jobs coletar_perfil)

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.drop_table("contas_coleta")
    op.drop_column("perfis", "proxima_coleta_em")
    op.execute("DELETE FROM jobs WHERE tipo = 'coletar_perfil'")
    # Perfis marcados inexistentes sem nunca terem sido coletados podem ser falsos
    # positivos do bloqueio do instaloader: voltam a ativos para a primeira coleta.
    op.execute(
        "UPDATE perfis SET status = 'ativo' WHERE status = 'inexistente' AND ultima_coleta_em IS NULL"
    )


def downgrade() -> None:
    # Recria a estrutura vazia; não restaura contas, jobs nem status apagados.
    op.add_column("perfis", sa.Column("proxima_coleta_em", TS))
    op.create_table(
        "contas_coleta",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("usuario_ig", sa.Text, nullable=False, unique=True),
        sa.Column("sessao_criptografada", sa.Text),
        sa.Column("status", sa.String, nullable=False, server_default="ativa"),
        sa.Column("bloqueada_ate", TS),
        sa.Column("ultimo_uso_em", TS),
        sa.Column("usos_janela", sa.Integer, nullable=False, server_default="0"),
        sa.Column("janela_inicio", TS),
        sa.CheckConstraint(
            "status IN ('ativa', 'bloqueada', 'desativada')", name="ck_contas_coleta_status"
        ),
    )
