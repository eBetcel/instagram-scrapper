"""usuários, convites, sessões e grupos; perfis.fixo

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def _criado_em():
    return sa.Column("criado_em", TS, nullable=False, server_default=sa.func.now())


def _fk_usuario(**kw):
    return sa.Column(
        "usuario_id", sa.Integer, sa.ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False, **kw,
    )


def upgrade() -> None:
    op.add_column("perfis", sa.Column("fixo", sa.Boolean, nullable=False, server_default=sa.false()))
    # Perfis existentes foram cadastrados pela CLI: continuam sendo coletados.
    op.execute("UPDATE perfis SET fixo = true")

    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.Text, nullable=False, unique=True),
        sa.Column("nome", sa.Text, nullable=False),
        _criado_em(),
    )
    op.create_table(
        "convites",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("codigo_hash", sa.Text, nullable=False, unique=True),
        sa.Column("usos_restantes", sa.Integer, nullable=False),
        sa.Column("expira_em", TS),
        _criado_em(),
        sa.CheckConstraint("usos_restantes >= 0", name="ck_convites_usos"),
    )
    for tabela, extra in (("tokens_login", [sa.Column("usado_em", TS)]), ("sessoes", [])):
        op.create_table(
            tabela,
            sa.Column("id", sa.Integer, primary_key=True),
            _fk_usuario(),
            sa.Column("token_hash", sa.Text, nullable=False, unique=True),
            sa.Column("expira_em", TS, nullable=False),
            *extra,
            _criado_em(),
        )
        op.create_index(f"ix_{tabela}_usuario_id", tabela, ["usuario_id"])
    op.create_table(
        "grupos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("dono_id", sa.Integer, sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nome", sa.Text, nullable=False),
        sa.Column("descricao", sa.Text),
        sa.Column("slug", sa.Text, nullable=False, unique=True),
        _criado_em(),
    )
    op.create_index("ix_grupos_dono_id", "grupos", ["dono_id"])
    op.create_table(
        "grupo_perfis",
        sa.Column("grupo_id", sa.Integer, sa.ForeignKey("grupos.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("perfil_id", sa.Integer, sa.ForeignKey("perfis.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("adicionado_em", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_grupo_perfis_perfil_id", "grupo_perfis", ["perfil_id"])
    op.create_table(
        "grupo_seguidores",
        sa.Column("grupo_id", sa.Integer, sa.ForeignKey("grupos.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "usuario_id", sa.Integer, sa.ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("seguido_em", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_grupo_seguidores_usuario_id", "grupo_seguidores", ["usuario_id"])


def downgrade() -> None:
    for tabela in ("grupo_seguidores", "grupo_perfis", "grupos", "sessoes", "tokens_login",
                   "convites", "usuarios"):
        op.drop_table(tabela)
    op.drop_column("perfis", "fixo")
