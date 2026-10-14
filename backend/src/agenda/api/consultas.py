"""Consultas de eventos para a agenda, o grupo público e o detalhe."""

from datetime import date, datetime, time, timedelta

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from agenda.api.esquemas import EventoResumo
from agenda.extracao.regras import FUSO
from agenda.models import Evento, EventoFonte, Grupo, GrupoPerfil, GrupoSeguidor, Post

LIMITE_EVENTOS = 500
JANELA_ALTERADO = timedelta(days=7)


def _no_periodo(stmt: Select, de: date, ate: date) -> Select:
    inicio = datetime.combine(de, time.min, FUSO)
    fim = datetime.combine(ate + timedelta(days=1), time.min, FUSO)
    return stmt.where(Evento.inicio >= inicio, Evento.inicio < fim)


def _com_fonte_de(perfis) -> Select:
    """Eventos com ao menos uma fonte cujo post é de um dos `perfis` (subconsulta de ids)."""
    return select(Evento).where(
        select(EventoFonte.id)
        .join(Post, Post.id == EventoFonte.post_id)
        .where(EventoFonte.evento_id == Evento.id, Post.perfil_id.in_(perfis))
        .exists()
    )


def eventos_da_agenda(
    s: Session, usuario_id: int, de: date, ate: date, *,
    grupo: str | None = None, categoria: str | None = None, gratuito: bool = False,
) -> list[Evento]:
    grupos = select(Grupo.id).where(or_(
        Grupo.dono_id == usuario_id,
        Grupo.id.in_(select(GrupoSeguidor.grupo_id).where(GrupoSeguidor.usuario_id == usuario_id)),
    ))
    if grupo:
        grupos = grupos.where(Grupo.slug == grupo)
    perfis = select(GrupoPerfil.perfil_id).where(GrupoPerfil.grupo_id.in_(grupos))
    stmt = _no_periodo(_com_fonte_de(perfis), de, ate)
    if categoria:
        stmt = stmt.where(Evento.categoria == categoria)
    if gratuito:
        stmt = stmt.where(or_(Evento.gratuito.is_(True), Evento.preco_max == 0))
    return list(s.scalars(stmt.order_by(Evento.inicio, Evento.id).limit(LIMITE_EVENTOS)))


def eventos_do_grupo(s: Session, grupo_id: int, de: date, ate: date) -> list[Evento]:
    perfis = select(GrupoPerfil.perfil_id).where(GrupoPerfil.grupo_id == grupo_id)
    stmt = _no_periodo(_com_fonte_de(perfis), de, ate)
    return list(s.scalars(stmt.order_by(Evento.inicio, Evento.id).limit(LIMITE_EVENTOS)))


def resumir(s: Session, eventos: list[Evento], agora: datetime) -> list[EventoResumo]:
    """`alterado` e `imagem` calculados em lote (duas consultas para a lista inteira)."""
    ids = [e.id for e in eventos]
    alterados = set(s.scalars(
        select(EventoFonte.evento_id).where(
            EventoFonte.evento_id.in_(ids), EventoFonte.decisao == "atualizacao",
            EventoFonte.criado_em > agora - JANELA_ALTERADO,
        )
    ))
    imagens: dict[int, str] = {}
    for evento_id, shortcode, n_imagens in s.execute(
        select(EventoFonte.evento_id, Post.shortcode, Post.imagens)
        .join(Post, Post.id == EventoFonte.post_id)
        .where(EventoFonte.evento_id.in_(ids))
        .order_by(EventoFonte.evento_id, Post.publicado_em.asc().nulls_last(), Post.id)
    ):
        if evento_id not in imagens and n_imagens:
            imagens[evento_id] = f"/api/posts/{shortcode}/imagens/0"
    return [
        EventoResumo(
            **{c: getattr(e, c) for c in EventoResumo.model_fields if c not in ("alterado", "imagem")},
            alterado=e.id in alterados, imagem=imagens.get(e.id),
        )
        for e in eventos
    ]
