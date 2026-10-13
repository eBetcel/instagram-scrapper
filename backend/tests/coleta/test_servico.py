import random
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from agenda.coleta.base import (
    ContaBloqueada,
    FakeColetor,
    PerfilInexistente,
    PerfilPrivado,
    PostColetado,
)
from agenda.coleta.servico import agendar_coletas, coletar_perfil
from agenda.models import Job, Perfil, Post
from agenda.storage import MemoriaStorage

AGORA = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


def baixar(url: str) -> bytes:
    return b"img:" + url.encode()


def post(sc, dias=1, imgs=1, fixado=False):
    return PostColetado(
        shortcode=sc,
        legenda=f"legenda {sc}",
        publicado_em=AGORA - timedelta(days=dias),
        urls_imagens=[f"http://x/{sc}/{i}" for i in range(imgs)],
        fixado=fixado,
    )


@pytest.fixture
def perfil(session):
    p = Perfil(username="casa")
    session.add(p)
    session.flush()
    return p


class ColetorEspia(FakeColetor):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.desde = "nunca"

    def posts_desde(self, username, desde):
        self.desde = desde
        return super().posts_desde(username, desde)


def rodar(s, perfil, posts, storage=None, coletor=None):
    storage = storage or MemoriaStorage()
    coletor = coletor or FakeColetor({"casa": posts})
    n = coletar_perfil(s, perfil.id, coletor, storage, agora=AGORA, baixar=baixar,
                       intervalo_horas=6)
    return n, storage


def test_primeira_coleta_busca_30_dias(session, perfil):
    c = ColetorEspia({"casa": [post("a")]})
    n, _ = rodar(session, perfil, [], coletor=c)
    assert c.desde == AGORA - timedelta(days=30)
    n, _ = rodar(session, perfil, [], coletor=c)
    assert c.desde == AGORA  # ultima_coleta_em da coleta anterior
    assert perfil.ultima_coleta_em == AGORA
    assert perfil.proxima_coleta_em == AGORA + timedelta(hours=6)


def test_coleta_incremental_para_no_shortcode_conhecido(session, perfil):
    session.add(Post(perfil_id=perfil.id, shortcode="velho"))
    session.flush()
    posts = [post("n1"), post("n2"), post("n3"), post("n4"), post("velho"), post("mais_velho")]
    n, _ = rodar(session, perfil, posts)
    assert n == 4
    codes = set(session.scalars(select(Post.shortcode)))
    assert "mais_velho" not in codes and {"n1", "n4"} <= codes


def test_conhecido_fixado_nao_para_a_coleta(session, perfil):
    session.add(Post(perfil_id=perfil.id, shortcode="fix"))
    session.flush()
    n, _ = rodar(session, perfil, [post("fix", dias=100, fixado=True), post("novo")])
    assert n == 1
    assert session.scalar(select(Post.id).where(Post.shortcode == "novo")) is not None


def test_tres_primeiros_conhecidos_sao_pulados(session, perfil):
    session.add_all([Post(perfil_id=perfil.id, shortcode=f"k{i}") for i in range(3)])
    session.flush()
    n, _ = rodar(session, perfil, [post("k0"), post("k1"), post("k2"), post("novo")])
    assert n == 1


def test_post_mais_velho_que_desde_nao_e_salvo(session, perfil):
    posts = [post("p0", dias=100), post("p1", dias=100), post("p2", dias=100),
             post("dentro"), post("fora", dias=40), post("depois")]
    n, _ = rodar(session, perfil, posts)
    codes = set(session.scalars(select(Post.shortcode)))
    assert codes == {"dentro"} and n == 1


def test_post_so_com_video_sem_imagem_vira_post_sem_imagens(session, perfil):
    n, st = rodar(session, perfil, [post("v", imgs=0)])
    p = session.scalar(select(Post).where(Post.shortcode == "v"))
    assert n == 1 and p.imagens == [] and p.status == "pendente"


def test_carrossel_de_10_imagens_salva_as_10(session, perfil):
    n, st = rodar(session, perfil, [post("c", imgs=10)])
    p = session.scalar(select(Post).where(Post.shortcode == "c"))
    assert p.imagens == [f"posts/c/{i}.jpg" for i in range(10)]
    assert st.ler("posts/c/9.jpg") == b"img:http://x/c/9"
    j = session.scalar(select(Job).where(Job.tipo == "extrair_post"))
    assert j.chave == f"extrair:{p.id}" and j.payload == {"post_id": p.id}


@pytest.mark.parametrize(
    "exc,status", [(PerfilPrivado(), "privado"), (PerfilInexistente(), "inexistente")]
)
def test_perfil_inacessivel_atualiza_status_e_nao_levanta(session, perfil, exc, status):
    c = FakeColetor({}, erros={"casa": exc})
    assert coletar_perfil(session, perfil.id, c, MemoriaStorage(), agora=AGORA, baixar=baixar,
                          intervalo_horas=6) == 0
    assert perfil.status == status


def test_conta_bloqueada_propaga_sem_atualizar_datas(session, perfil):
    c = FakeColetor({}, erros={"casa": ContaBloqueada()})
    with pytest.raises(ContaBloqueada):
        coletar_perfil(session, perfil.id, c, MemoriaStorage(), agora=AGORA, baixar=baixar,
                       intervalo_horas=6)
    assert perfil.ultima_coleta_em is None and perfil.proxima_coleta_em is None


def test_falha_de_download_nao_deixa_post_parcial(session, perfil):
    def ruim(url):
        raise OSError("falhou")

    with pytest.raises(OSError):
        coletar_perfil(session, perfil.id, FakeColetor({"casa": [post("a")]}),
                       MemoriaStorage(), agora=AGORA, baixar=ruim, intervalo_horas=6)
    assert session.scalar(select(Post.id)) is None


def test_shortcode_ja_existente_nao_duplica(session, perfil, monkeypatch):
    # Outro job insere o shortcode depois da checagem de conhecidos: ON CONFLICT cobre.
    import agenda.coleta.servico as sv

    monkeypatch.setattr(sv, "_conhecidos", lambda s, codes: set())
    session.add(Post(perfil_id=perfil.id, shortcode="dup"))
    session.flush()
    n, st = rodar(session, perfil, [post("dup")])
    assert n == 0
    assert len(list(session.scalars(select(Post).where(Post.shortcode == "dup")))) == 1
    assert session.scalar(select(Job).where(Job.tipo == "extrair_post")) is None


def test_agendar_nao_duplica_job_pendente(session, perfil):
    rng = random.Random(1)
    assert agendar_coletas(session, AGORA, rng=rng) == 1  # proxima NULL e devida
    assert agendar_coletas(session, AGORA, rng=rng) == 0
    j = session.scalar(select(Job).where(Job.tipo == "coletar_perfil"))
    assert j.chave == f"coletar:{perfil.id}" and j.payload == {"perfil_id": perfil.id}
    assert AGORA <= j.executar_em <= AGORA + timedelta(minutes=30)


def test_agendar_ignora_futuros_e_inativos(session):
    session.add_all([
        Perfil(username="fut", proxima_coleta_em=AGORA + timedelta(hours=1)),
        Perfil(username="priv", status="privado"),
        Perfil(username="ok", proxima_coleta_em=AGORA),
    ])
    session.flush()
    assert agendar_coletas(session, AGORA) == 1


def test_intervalo_padrao_vem_das_settings(session, perfil, monkeypatch):
    from agenda.config import get_settings

    monkeypatch.setenv("OPENAI_MODELO_EXTRACAO", "x")
    monkeypatch.setenv("OPENAI_MODELO_RECONCILIACAO", "y")
    monkeypatch.setenv("INTERVALO_COLETA_HORAS", "3")
    get_settings.cache_clear()
    try:
        coletar_perfil(session, perfil.id, FakeColetor({}), MemoriaStorage(),
                       agora=AGORA, baixar=baixar)
    finally:
        get_settings.cache_clear()
    assert perfil.proxima_coleta_em == AGORA + timedelta(hours=3)
