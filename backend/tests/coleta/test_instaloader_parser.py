import json
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


def test_parse_carrossel_retorna_todas_as_imagens():
    p = parse_post(_carregar("carrossel.json"))
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
    p = parse_post(_carregar("video.json"))
    assert p.urls_imagens == ["https://cdn.example/vid_capa.jpg"]
    assert p.fixado is True


def test_parse_legenda_ausente_vira_string_vazia():
    p = parse_post(_carregar("sem_legenda.json"))
    assert p.legenda == ""
    assert p.urls_imagens == ["https://cdn.example/img.jpg"]


def test_parse_sem_chave_de_legenda():
    node = _carregar("sem_legenda.json")
    del node["edge_media_to_caption"]
    assert parse_post(node).legenda == ""


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
            yield type("P", (), {"_node": i})()


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


def test_para_em_post_nao_fixado_mais_antigo_que_desde_e_ignora_fixado():
    pool = _Pool()
    fixado_antigo = {**_carregar("video.json"), "taken_at_timestamp": 1000}
    novo = _carregar("sem_legenda.json")  # 1760007200
    velho = {**_carregar("carrossel.json"), "taken_at_timestamp": 1500}
    depois = {**_carregar("carrossel.json"), "shortcode": "NUNCA"}
    perfil = _Perfil([fixado_antigo, novo, velho, depois])
    desde = datetime.fromtimestamp(1760000000, UTC)
    got = list(_coletor(pool, lambda u: perfil).posts_desde("a", desde))
    assert [p.shortcode for p in got] == ["VID0001", "IMG0001"]
