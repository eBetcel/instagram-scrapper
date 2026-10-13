from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from agenda.models import Evento, EventoFonte, Perfil, Post


def _perfil(session, username="casa"):
    p = Perfil(username=username)
    session.add(p)
    session.flush()
    return p


def _post(session, perfil, shortcode="abc"):
    p = Post(perfil_id=perfil.id, shortcode=shortcode)
    session.add(p)
    session.flush()
    return p


def _evento(session, categoria="show"):
    e = Evento(
        titulo="Show",
        inicio=datetime(2030, 1, 1, 20, tzinfo=UTC),
        categoria=categoria,
    )
    session.add(e)
    session.flush()
    return e


def test_shortcode_duplicado_levanta_integrity_error(session):
    perfil = _perfil(session)
    _post(session, perfil, "dup")
    with pytest.raises(IntegrityError):
        _post(session, perfil, "dup")


def test_username_unico(session):
    _perfil(session, "mesmo")
    with pytest.raises(IntegrityError):
        _perfil(session, "mesmo")


def test_evento_fonte_duplicada_levanta_integrity_error(session):
    post = _post(session, _perfil(session))
    ev = _evento(session)
    session.add(EventoFonte(evento_id=ev.id, post_id=post.id, decisao="novo"))
    session.flush()
    with pytest.raises(IntegrityError):
        session.add(EventoFonte(evento_id=ev.id, post_id=post.id, decisao="novo"))
        session.flush()


def test_categoria_invalida_rejeitada(session):
    with pytest.raises(IntegrityError):
        _evento(session, categoria="inexistente")


def test_artistas_norm_default_vazio(session):
    assert _evento(session).artistas_norm == []


def test_pg_trgm_disponivel(session):
    assert session.execute(text("SELECT similarity('abc','abd')")).scalar() > 0
