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


def test_perfil_novo_nao_e_fixo_por_padrao(session):
    from agenda.models import Perfil as P
    p = P(username="novo_perfil")
    session.add(p)
    session.flush()
    session.refresh(p)
    assert p.fixo is False


def test_apagar_grupo_apaga_perfis_e_seguidores_do_grupo(session):
    from sqlalchemy import delete, func, select

    from agenda.models import Grupo, GrupoPerfil, GrupoSeguidor, Perfil as P, Usuario

    dono, fa = Usuario(email="a@x.com", nome="A"), Usuario(email="b@x.com", nome="B")
    p = P(username="casa_cascata")
    session.add_all([dono, fa, p])
    session.flush()
    g = Grupo(dono_id=dono.id, nome="G", slug="g")
    session.add(g)
    session.flush()
    session.add_all([GrupoPerfil(grupo_id=g.id, perfil_id=p.id), GrupoSeguidor(grupo_id=g.id, usuario_id=fa.id)])
    session.flush()
    session.execute(delete(Grupo).where(Grupo.id == g.id))
    assert session.scalar(select(func.count()).select_from(GrupoPerfil)) == 0
    assert session.scalar(select(func.count()).select_from(GrupoSeguidor)) == 0
