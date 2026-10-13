import json
from types import SimpleNamespace
from datetime import UTC, datetime
from pathlib import Path

import instaloader
import pytest

from agenda.coleta.base import (
    ContaBloqueada,
    FakeColetor,
    PerfilInexistente,
    PerfilPrivado,
    PostColetado,
)
from agenda.coleta.instaloader_coletor import InstaloaderColetor, parse_post

FIX = Path(__file__).parent.parent / "fixtures" / "ig"


def _carregar(nome: str) -> dict:
    return json.loads((FIX / nome).read_text())


def _ctx(logado: bool):
    return SimpleNamespace(iphone_support=True, is_logged_in=logado, error=lambda *a, **k: None)


def _post_anonimo(node: dict) -> instaloader.Post:
    """Node GraphQL anônimo, como `Post(context, node)` sem sessão."""
    return instaloader.Post(_ctx(False), node)


def test_parse_carrossel_retorna_todas_as_imagens():
    p = parse_post(_post_anonimo(_carregar("carrossel.json")))
    assert p.shortcode == "CAR0001"
    assert p.legenda.startswith("Show da banda X")
    assert p.urls_imagens == [
        "https://cdn.example/car_1.jpg",
        "https://cdn.example/car_2.jpg",
        "https://cdn.example/car_3_capa.jpg",
    ]
    assert p.publicado_em == datetime.fromtimestamp(1760000000, UTC)
    assert p.publicado_em.tzinfo is not None
    assert p.fixado is False


def test_parse_video_usa_capa():
    p = parse_post(_post_anonimo(_carregar("video.json")))
    assert p.urls_imagens == ["https://cdn.example/vid_capa.jpg"]
    assert p.fixado is True


def test_parse_legenda_ausente_vira_string_vazia():
    p = parse_post(_post_anonimo(_carregar("sem_legenda.json")))
    assert p.legenda == ""
    assert p.urls_imagens == ["https://cdn.example/img.jpg"]


def test_parse_sem_chave_de_legenda():
    node = _carregar("sem_legenda.json")
    del node["edge_media_to_caption"]
    assert parse_post(_post_anonimo(node)).legenda == ""


def test_fake_coletor_devolve_posts_e_erros():
    p = PostColetado("a", "x", datetime(2026, 1, 1, tzinfo=UTC), [])
    f = FakeColetor({"ok": [p]}, erros={"priv": PerfilPrivado()})
    assert list(f.posts_desde("ok", None)) == [p]
    with pytest.raises(PerfilPrivado):
        list(f.posts_desde("priv", None))


# --- mapeamento de exceções, sem rede ---


class _Pool:
    def __init__(self):
        self.conta = type("C", (), {"id": 1, "usuario_ig": "u", "sessao_criptografada": None})()
        self.bloqueios = []

    def obter(self):
        return self.conta

    def marcar_bloqueada(self, conta, ate):
        self.bloqueios.append((conta, ate))


class _Perfil:
    def __init__(self, itens):
        self._itens = itens

    def get_posts(self):
        for i in self._itens:
            if isinstance(i, Exception):
                raise i
            yield _post_anonimo(i)


def _coletor(pool, fabrica):
    return InstaloaderColetor(pool, fabrica_perfil=lambda conta, username: fabrica(username))


def _levanta(exc):
    def f(username):
        raise exc

    return f


@pytest.mark.parametrize(
    "exc,esperado",
    [
        (instaloader.ProfileNotExistsException("x"), PerfilInexistente),
        (instaloader.PrivateProfileNotFollowedException("x"), PerfilPrivado),
    ],
)
def test_mapeia_erros_de_perfil(exc, esperado):
    pool = _Pool()
    with pytest.raises(esperado):
        list(_coletor(pool, _levanta(exc)).posts_desde("a", None))
    assert pool.bloqueios == []


@pytest.mark.parametrize(
    "exc",
    [
        instaloader.LoginRequiredException("login"),
        instaloader.TooManyRequestsException("429 Too Many Requests"),
        instaloader.ConnectionException("401 Unauthorized"),
        instaloader.ConnectionException("checkpoint required"),
        instaloader.ConnectionException("Please wait a few minutes"),
    ],
)
def test_bloqueio_marca_conta_e_levanta(exc):
    pool = _Pool()
    antes = datetime.now(UTC)
    with pytest.raises(ContaBloqueada):
        list(_coletor(pool, _levanta(exc)).posts_desde("a", None))
    (conta, ate), = pool.bloqueios
    assert conta is pool.conta
    assert 5.9 * 3600 < (ate - antes).total_seconds() < 6.1 * 3600


def test_bloqueio_durante_iteracao():
    pool = _Pool()
    node = _carregar("carrossel.json")
    perfil = _Perfil([node, instaloader.TooManyRequestsException("429")])
    c = _coletor(pool, lambda u: perfil)
    it = c.posts_desde("a", None)
    assert next(iter(it)).shortcode == "CAR0001"
    with pytest.raises(ContaBloqueada):
        list(it)


def test_connection_exception_comum_propaga():
    pool = _Pool()
    with pytest.raises(instaloader.ConnectionException):
        list(_coletor(pool, _levanta(instaloader.ConnectionException("500 boom"))).posts_desde("a", None))
    assert pool.bloqueios == []


def _node(sc, ts, **kw):
    return {**_carregar("sem_legenda.json"), "shortcode": sc, "taken_at_timestamp": ts, **kw}


def test_primeiros_posts_sao_isentos_da_regra_de_parada():
    pool = _Pool()
    desde = datetime.fromtimestamp(1760000000, UTC)
    # primeiro velho sem marcador de fixado, seguido de novos
    perfil = _Perfil([_node("VELHO", 1000), _node("N1", 1760000100), _node("N2", 1760000200)])
    got = list(_coletor(pool, lambda u: perfil).posts_desde("a", desde))
    assert [p.shortcode for p in got] == ["VELHO", "N1", "N2"]


def test_regra_de_parada_vale_a_partir_do_quarto_post():
    pool = _Pool()
    desde = datetime.fromtimestamp(1760000000, UTC)
    itens = [_node(f"A{i}", 1000 + i) for i in range(3)]  # 3 velhos no topo (isentos)
    itens += [_node("N1", 1760000100), _node("VELHO4", 1000), _node("NUNCA", 1760000300)]
    got = list(_coletor(pool, lambda u: _Perfil(itens)).posts_desde("a", desde))
    assert [p.shortcode for p in got] == ["A0", "A1", "A2", "N1"]


def test_fixado_apos_o_terceiro_tambem_e_isento():
    pool = _Pool()
    desde = datetime.fromtimestamp(1760000000, UTC)
    itens = [_node(f"N{i}", 1760000100 + i) for i in range(3)]
    itens += [_node("FIX", 1000, pinned_for_users=[{"id": "1"}]), _node("VELHO", 1000)]
    got = list(_coletor(pool, lambda u: _Perfil(itens)).posts_desde("a", desde))
    assert [p.shortcode for p in got] == ["N0", "N1", "N2", "FIX"]


# --- formato iPhone (Profile.get_posts() logado usa Post.from_iphone_struct) ---


def _post_iphone(nome: str) -> instaloader.Post:
    return instaloader.Post.from_iphone_struct(_ctx(True), _carregar(f"iphone/{nome}"))


class _PerfilDePosts:
    def __init__(self, posts):
        self._posts = posts

    def get_posts(self):
        yield from self._posts


def test_coletor_le_posts_no_formato_iphone():
    pool = _Pool()
    posts = [_post_iphone("video.json"), _post_iphone("carrossel.json"), _post_iphone("imagem_sem_legenda.json")]
    got = list(_coletor(pool, lambda u: _PerfilDePosts(posts)).posts_desde("a", None))
    vid, car, img = got
    assert car.shortcode == "ICAR001"
    assert car.legenda == "Agenda de outubro: dia 10 show, dia 17 festa"
    assert car.publicado_em == datetime.fromtimestamp(1760010000, UTC)
    assert car.urls_imagens == [
        "https://cdn.example/ic_1.jpg?stp=x&_nc_ht=y",
        "https://cdn.example/ic_2.jpg",
        "https://cdn.example/ic_3_capa.jpg",
    ]
    assert car.fixado is False
    assert vid.urls_imagens == ["https://cdn.example/iv_capa.jpg"]
    assert vid.legenda == "Teaser do festival"
    assert vid.fixado is True
    assert img.legenda == ""
    assert img.urls_imagens == ["https://cdn.example/ii.jpg?stp=a"]
    assert img.publicado_em.tzinfo is not None


def test_perfil_privado_nao_seguido_levanta_perfil_privado():
    pool = _Pool()
    perfil = _PerfilDePosts([_post_iphone("carrossel.json")])
    perfil.is_private, perfil.followed_by_viewer = True, False
    with pytest.raises(PerfilPrivado):
        list(_coletor(pool, lambda u: perfil).posts_desde("a", None))
    assert pool.bloqueios == []


def test_perfil_privado_seguido_e_coletado():
    pool = _Pool()
    perfil = _PerfilDePosts([_post_iphone("carrossel.json")])
    perfil.is_private, perfil.followed_by_viewer = True, True
    got = list(_coletor(pool, lambda u: perfil).posts_desde("a", None))
    assert [p.shortcode for p in got] == ["ICAR001"]
