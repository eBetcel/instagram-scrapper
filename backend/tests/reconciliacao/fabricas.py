"""Fabricas compartilhadas pelos testes de reconciliacao."""

from datetime import datetime, timedelta, timezone

from agenda.extracao.schema import Confianca, EventoExtraido
from agenda.models import Evento, Perfil, Post
from agenda.reconciliacao.candidatos import normalizar_artistas

AGORA = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def extraido(**kw) -> EventoExtraido:
    base = dict(
        titulo=None, descricao=None, data_inicio=None, hora_inicio=None, data_fim=None,
        hora_fim=None, local_nome=None, endereco=None, cidade=None, categoria="show",
        preco_texto=None, gratuito=None, preco_min=None, preco_max=None, link_ingresso=None,
        artistas=[], festival=None, status_indicado=None,
        confianca=Confianca(data_inicio=1.0, hora_inicio=1.0, local_nome=1.0),
    )
    base.update(kw)
    return EventoExtraido(**base)


def evento(s, titulo="Evento Qualquer", inicio=None, **kw) -> Evento:
    artistas = kw.pop("artistas", [])
    ev = Evento(
        titulo=titulo,
        inicio=inicio or AGORA + timedelta(days=10),
        categoria=kw.pop("categoria", "show"),
        status=kw.pop("status", "ativo"),
        artistas=artistas,
        artistas_norm=normalizar_artistas(artistas),
        **kw,
    )
    s.add(ev)
    s.flush()
    return ev


def post(s, shortcode="P1", username="casa", legenda="legenda do post") -> Post:
    perfil = s.query(Perfil).filter_by(username=username).one_or_none()
    if perfil is None:
        perfil = Perfil(username=username)
        s.add(perfil)
        s.flush()
    p = Post(perfil_id=perfil.id, shortcode=shortcode, legenda=legenda, publicado_em=AGORA)
    s.add(p)
    s.flush()
    return p
