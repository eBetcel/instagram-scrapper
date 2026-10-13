"""esquema inicial

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def _in(coluna, valores):
    return f"{coluna} IN ({', '.join(repr(v) for v in valores)})"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "perfis",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.Text, nullable=False, unique=True),
        sa.Column("status", sa.String, nullable=False, server_default="ativo"),
        sa.Column("ultima_coleta_em", TS),
        sa.Column("proxima_coleta_em", TS),
        sa.Column("criado_em", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(_in("status", ("ativo", "privado", "inexistente")), name="ck_perfis_status"),
    )
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
        sa.CheckConstraint(_in("status", ("ativa", "bloqueada", "desativada")), name="ck_contas_coleta_status"),
    )
    op.create_table(
        "posts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("perfil_id", sa.Integer, sa.ForeignKey("perfis.id"), nullable=False),
        sa.Column("shortcode", sa.Text, nullable=False, unique=True),
        sa.Column("legenda", sa.Text),
        sa.Column("publicado_em", TS),
        sa.Column("imagens", pg.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String, nullable=False, server_default="pendente"),
        sa.Column("extracao", pg.JSONB),
        sa.Column("modelo_extracao", sa.Text),
        sa.Column("tokens_entrada", sa.Integer),
        sa.Column("tokens_saida", sa.Integer),
        sa.Column("custo_estimado", sa.Numeric(12, 6)),
        sa.Column("erro_msg", sa.Text),
        sa.Column("criado_em", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            _in("status", ("pendente", "extraido", "reconciliado", "erro")), name="ck_posts_status"
        ),
    )
    op.create_index("ix_posts_perfil_id", "posts", ["perfil_id"])

    op.create_table(
        "eventos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("titulo", sa.Text, nullable=False),
        sa.Column("descricao", sa.Text),
        sa.Column("inicio", TS, nullable=False),
        sa.Column("fim", TS),
        sa.Column("hora_definida", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("local_nome", sa.Text),
        sa.Column("endereco", sa.Text),
        sa.Column("cidade", sa.Text),
        sa.Column("categoria", sa.String, nullable=False),
        sa.Column("preco_texto", sa.Text),
        sa.Column("gratuito", sa.Boolean),
        sa.Column("preco_min", sa.Numeric(10, 2)),
        sa.Column("preco_max", sa.Numeric(10, 2)),
        sa.Column("link_ingresso", sa.Text),
        sa.Column("artistas", pg.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("artistas_norm", pg.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String, nullable=False, server_default="ativo"),
        sa.Column("criado_em", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("atualizado_em", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            _in(
                "categoria",
                ("show", "festa", "exposicao", "teatro", "cinema", "oficina", "festival", "outro"),
            ),
            name="ck_eventos_categoria",
        ),
        sa.CheckConstraint(
            _in("status", ("ativo", "adiado", "cancelado", "esgotado")), name="ck_eventos_status"
        ),
    )
    op.create_index("ix_eventos_inicio", "eventos", ["inicio"])
    op.create_index(
        "ix_eventos_titulo_trgm", "eventos", ["titulo"],
        postgresql_using="gin", postgresql_ops={"titulo": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_eventos_local_nome_trgm", "eventos", ["local_nome"],
        postgresql_using="gin", postgresql_ops={"local_nome": "gin_trgm_ops"},
    )
    op.create_index("ix_eventos_artistas_norm", "eventos", ["artistas_norm"], postgresql_using="gin")

    op.create_table(
        "evento_fontes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("evento_id", sa.Integer, sa.ForeignKey("eventos.id"), nullable=False),
        sa.Column("post_id", sa.Integer, sa.ForeignKey("posts.id"), nullable=False),
        sa.Column("decisao", sa.String, nullable=False),
        sa.Column("criado_em", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("evento_id", "post_id", name="uq_evento_fontes_evento_post"),
        sa.CheckConstraint(_in("decisao", ("novo", "duplicado", "atualizacao")), name="ck_evento_fontes_decisao"),
    )
    op.create_index("ix_evento_fontes_evento_id", "evento_fontes", ["evento_id"])
    op.create_index("ix_evento_fontes_post_id", "evento_fontes", ["post_id"])

    op.create_table(
        "revisoes_evento",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("evento_id", sa.Integer, sa.ForeignKey("eventos.id"), nullable=False),
        sa.Column("post_id", sa.Integer, sa.ForeignKey("posts.id")),
        sa.Column("campo", sa.Text, nullable=False),
        sa.Column("valor_anterior", sa.Text),
        sa.Column("valor_novo", sa.Text),
        sa.Column("motivo", sa.Text),
        sa.Column("criado_em", TS, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_revisoes_evento_evento_id", "revisoes_evento", ["evento_id"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("tipo", sa.Text, nullable=False),
        sa.Column("chave", sa.Text),
        sa.Column("payload", pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String, nullable=False, server_default="pendente"),
        sa.Column("tentativas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_tentativas", sa.Integer, nullable=False, server_default="5"),
        sa.Column("executar_em", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("erro_msg", sa.Text),
        sa.CheckConstraint(
            _in("status", ("pendente", "executando", "concluido", "erro")), name="ck_jobs_status"
        ),
    )
    op.create_index("ix_jobs_fila", "jobs", ["status", "executar_em"])
    op.create_index(
        "uq_jobs_tipo_chave_ativo", "jobs", ["tipo", "chave"], unique=True,
        postgresql_where=sa.text("chave IS NOT NULL AND status <> 'concluido'"),
    )


def downgrade() -> None:
    for t in ("jobs", "revisoes_evento", "evento_fontes", "eventos", "posts", "contas_coleta", "perfis"):
        op.drop_table(t)
