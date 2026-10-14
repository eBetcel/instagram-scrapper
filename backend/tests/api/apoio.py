"""Ajudantes dos testes da api."""

from datetime import UTC, datetime, timedelta

from agenda.api.seguranca import hash_valor, novo_token
from agenda.models import Sessao, Usuario


def logar(api, email="fulana@x.com", nome="Fulana", cliente=None) -> Usuario:
    """Cria usuário e sessão direto no banco e põe o cookie no cliente."""
    token = novo_token()
    with api.fabrica() as s:
        u = Usuario(email=email, nome=nome)
        s.add(u)
        s.flush()
        s.add(Sessao(usuario_id=u.id, token_hash=hash_valor(token),
                     expira_em=datetime.now(UTC) + timedelta(days=30)))
        s.commit()
    (cliente or api.cliente).cookies.set("sessao", token)
    return u


_contador = iter(range(1, 10**6))


def semear(api, username, titulo, inicio, *, decisao="novo", fonte_em=None, imagens=None,
           publicado_em=None, evento_id=None, **campos):
    """Cria (ou reaproveita) perfil, um post novo e um evento com fonte nesse post.
    Com `evento_id`, só acrescenta a fonte ao evento existente. Devolve (evento_id, shortcode)."""
    from agenda.models import Evento, EventoFonte, Perfil, Post
    from sqlalchemy import select

    with api.fabrica() as s:
        perfil = s.scalar(select(Perfil).where(Perfil.username == username))
        if perfil is None:
            perfil = Perfil(username=username, ultima_coleta_em=datetime.now(UTC))
            s.add(perfil)
            s.flush()
        sc = f"SC{next(_contador)}"
        post = Post(perfil_id=perfil.id, shortcode=sc, status="reconciliado",
                    imagens=imagens if imagens is not None else [f"posts/{sc}/0.jpg"],
                    publicado_em=publicado_em or datetime.now(UTC))
        s.add(post)
        s.flush()
        if evento_id is None:
            ev = Evento(titulo=titulo, inicio=inicio, categoria=campos.pop("categoria", "show"),
                        hora_definida=campos.pop("hora_definida", True), **campos)
            s.add(ev)
            s.flush()
            evento_id = ev.id
        fonte = EventoFonte(evento_id=evento_id, post_id=post.id, decisao=decisao)
        if fonte_em is not None:
            fonte.criado_em = fonte_em
        s.add(fonte)
        s.commit()
        return evento_id, sc


def grupo_com(api, slug_nome, *usernames, cliente=None):
    c = cliente or api.cliente
    slug = c.post("/api/grupos", json={"nome": slug_nome}).json()["slug"]
    for u in usernames:
        c.post(f"/api/grupos/{slug}/perfis", json={"username": u})
    return slug
