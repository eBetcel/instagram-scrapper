from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

CATEGORIAS = ("show", "festa", "exposicao", "teatro", "cinema", "oficina", "festival", "outro")


def _in(coluna: str, valores: tuple[str, ...]) -> str:
    return f"{coluna} IN ({', '.join(repr(v) for v in valores)})"


class Base(DeclarativeBase):
    pass


class Perfil(Base):
    __tablename__ = "perfis"
    __table_args__ = (
        CheckConstraint(_in("status", ("ativo", "privado", "inexistente")), name="ck_perfis_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(String, server_default="ativo", default="ativo")
    ultima_coleta_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    proxima_coleta_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContaColeta(Base):
    __tablename__ = "contas_coleta"
    __table_args__ = (
        CheckConstraint(_in("status", ("ativa", "bloqueada", "desativada")), name="ck_contas_coleta_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_ig: Mapped[str] = mapped_column(Text, unique=True)
    sessao_criptografada: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, server_default="ativa", default="ativa")
    bloqueada_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_uso_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    usos_janela: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    janela_inicio: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        CheckConstraint(
            _in("status", ("pendente", "extraido", "reconciliado", "erro")), name="ck_posts_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    perfil_id: Mapped[int] = mapped_column(ForeignKey("perfis.id"), index=True)
    shortcode: Mapped[str] = mapped_column(Text, unique=True)
    legenda: Mapped[str | None] = mapped_column(Text)
    publicado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    imagens: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'"), default=list
    )
    status: Mapped[str] = mapped_column(String, server_default="pendente", default="pendente")
    extracao: Mapped[dict | None] = mapped_column(JSONB)
    modelo_extracao: Mapped[str | None] = mapped_column(Text)
    tokens_entrada: Mapped[int | None] = mapped_column(Integer)
    tokens_saida: Mapped[int | None] = mapped_column(Integer)
    custo_estimado: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    erro_msg: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    perfil: Mapped[Perfil] = relationship()


class Evento(Base):
    __tablename__ = "eventos"
    __table_args__ = (
        CheckConstraint(_in("categoria", CATEGORIAS), name="ck_eventos_categoria"),
        CheckConstraint(
            _in("status", ("ativo", "adiado", "cancelado", "esgotado")), name="ck_eventos_status"
        ),
        Index("ix_eventos_inicio", "inicio"),
        Index("ix_eventos_titulo_trgm", "titulo", postgresql_using="gin", postgresql_ops={"titulo": "gin_trgm_ops"}),
        Index(
            "ix_eventos_local_nome_trgm",
            "local_nome",
            postgresql_using="gin",
            postgresql_ops={"local_nome": "gin_trgm_ops"},
        ),
        Index("ix_eventos_artistas_norm", "artistas_norm", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(Text)
    descricao: Mapped[str | None] = mapped_column(Text)
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fim: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hora_definida: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), default=True)
    local_nome: Mapped[str | None] = mapped_column(Text)
    endereco: Mapped[str | None] = mapped_column(Text)
    cidade: Mapped[str | None] = mapped_column(Text)
    categoria: Mapped[str] = mapped_column(String)
    preco_texto: Mapped[str | None] = mapped_column(Text)
    gratuito: Mapped[bool | None] = mapped_column(Boolean)
    preco_min: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    preco_max: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    link_ingresso: Mapped[str | None] = mapped_column(Text)
    artistas: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'"), default=list
    )
    artistas_norm: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'"), default=list
    )
    status: Mapped[str] = mapped_column(String, server_default="ativo", default="ativo")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EventoFonte(Base):
    __tablename__ = "evento_fontes"
    __table_args__ = (
        UniqueConstraint("evento_id", "post_id", name="uq_evento_fontes_evento_post"),
        CheckConstraint(_in("decisao", ("novo", "duplicado", "atualizacao")), name="ck_evento_fontes_decisao"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    evento_id: Mapped[int] = mapped_column(ForeignKey("eventos.id"), index=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    decisao: Mapped[str] = mapped_column(String)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RevisaoEvento(Base):
    __tablename__ = "revisoes_evento"

    id: Mapped[int] = mapped_column(primary_key=True)
    evento_id: Mapped[int] = mapped_column(ForeignKey("eventos.id"), index=True)
    post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id"))
    campo: Mapped[str] = mapped_column(Text)
    valor_anterior: Mapped[str | None] = mapped_column(Text)
    valor_novo: Mapped[str | None] = mapped_column(Text)
    motivo: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            _in("status", ("pendente", "executando", "concluido", "erro")), name="ck_jobs_status"
        ),
        Index(
            "uq_jobs_tipo_chave_ativo",
            "tipo",
            "chave",
            unique=True,
            postgresql_where=text("chave IS NOT NULL AND status <> 'concluido'"),
        ),
        Index("ix_jobs_fila", "status", "executar_em"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tipo: Mapped[str] = mapped_column(Text)
    chave: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), default=dict)
    status: Mapped[str] = mapped_column(String, server_default="pendente", default="pendente")
    tentativas: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    max_tentativas: Mapped[int] = mapped_column(Integer, server_default="5", default=5)
    executar_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    erro_msg: Mapped[str | None] = mapped_column(Text)
