import logging
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from agenda.coleta.base import FakeColetor, PostColetado, ResultadoLote
from agenda.coleta.servico import coletar_lote
from agenda.models import Job, LoteColeta, Perfil, Post
from agenda.storage import MemoriaStorage

AGORA = datetime(2030, 1, 1, 12, tzinfo=UTC)
PRECO = Decimal("0.0017")


def _baixar(url: str) -> bytes:
    return f"bytes:{url}".encode()


def _post(shortcode, perfil="casa", urls=("http://x/a.jpg",)):
    return PostColetado(
        shortcode=shortcode,
        legenda=f"legenda {shortcode}",
        publicado_em=datetime(2029, 12, 31, tzinfo=UTC),
        urls_imagens=list(urls),
        perfil=perfil,
    )


def _lote(s, perfis=("casa",), **kw):
    for u in perfis:
        if s.scalar(select(Perfil.id).where(Perfil.username == u)) is None:
            s.add(Perfil(username=u))
    lote = LoteColeta(tipo="novos", janela="30 days", limite=50, perfis=list(perfis), **kw)
    s.add(lote)
    s.flush()
    return lote


def _rodar(s, lote, coletor, storage=None, baixar=_baixar):
    storage = storage if storage is not None else MemoriaStorage()
    return coletar_lote(
        s, lote.id, coletor, storage, agora=AGORA, baixar=baixar, preco_por_post=PRECO
    )


def _perfil(s, username):
    return s.scalars(select(Perfil).where(Perfil.username == username)).one()


def test_grava_posts_novos_baixa_imagens_e_enfileira_extracao(session):
    lote = _lote(session)
    storage = MemoriaStorage()
    coletor = FakeColetor([_post("a1", urls=("http://x/0", "http://x/1"))])
    assert _rodar(session, lote, coletor, storage) == 1
    post = session.scalars(select(Post).where(Post.shortcode == "a1")).one()
    assert post.legenda == "legenda a1"
    assert post.status == "pendente"
    assert post.imagens == ["posts/a1/0.jpg", "posts/a1/1.jpg"]
    assert storage.ler("posts/a1/1.jpg") == b"bytes:http://x/1"
    job = session.scalars(select(Job).where(Job.tipo == "extrair_post")).one()
    assert job.payload == {"post_id": post.id}
    assert job.chave == f"extrair:{post.id}"


def test_shortcode_existente_e_ignorado(session):
    lote = _lote(session)
    existente = Post(perfil_id=_perfil(session, "casa").id, shortcode="a1")
    session.add(existente)
    session.flush()
    baixados = []

    def baixar(url):
        baixados.append(url)
        return b"x"

    assert _rodar(session, lote, FakeColetor([_post("a1"), _post("a2")]), baixar=baixar) == 1
    assert baixados == ["http://x/a.jpg"]  # só o de a2
    assert session.scalars(select(Post)).all().__len__() == 2
    assert session.scalars(select(Job).where(Job.tipo == "extrair_post")).all().__len__() == 1


def test_mesmo_shortcode_duas_vezes_no_lote_grava_uma_vez(session):
    lote = _lote(session, perfis=("casa", "bar"))
    coletor = FakeColetor([_post("a1", "casa"), _post("a1", "bar")])
    assert _rodar(session, lote, coletor) == 1
    assert lote.posts == 2
    assert lote.posts_novos == 1


def test_quebra_em_execucoes_de_50(session):
    nomes = [f"p{i:03d}" for i in range(120)]
    lote = _lote(session, perfis=nomes)
    coletor = FakeColetor([])
    _rodar(session, lote, coletor)
    assert [len(c[0]) for c in coletor.chamadas] == [50, 50, 20]
    assert coletor.chamadas[0][1:] == ("30 days", 50)


def test_erro_inexistente_muda_status(session):
    lote = _lote(session, perfis=("sumiu", "ok"))
    coletor = FakeColetor([], erros={"sumiu": "Profile does not exist"})
    _rodar(session, lote, coletor)
    assert _perfil(session, "sumiu").status == "inexistente"
    assert _perfil(session, "ok").status == "ativo"


def test_erro_desconhecido_mantem_ativo_e_registra_warning(session, caplog):
    lote = _lote(session, perfis=("casa",))
    coletor = FakeColetor([], erros={"casa": "algo estranho"})
    with caplog.at_level(logging.WARNING):
        _rodar(session, lote, coletor)
    assert _perfil(session, "casa").status == "ativo"
    assert any(
        r.levelno == logging.WARNING and "casa" in r.getMessage() for r in caplog.records
    )


def test_imagem_que_falha_e_pulada_e_post_salvo_com_as_outras(session, caplog):
    lote = _lote(session)
    storage = MemoriaStorage()

    def baixar(url):
        if url.endswith("/1"):
            raise OSError("boom")
        return url.encode()

    coletor = FakeColetor([_post("a1", urls=("http://x/0", "http://x/1", "http://x/2"))])
    with caplog.at_level(logging.WARNING):
        assert _rodar(session, lote, coletor, storage, baixar) == 1
    post = session.scalars(select(Post)).one()
    assert post.imagens == ["posts/a1/0.jpg", "posts/a1/1.jpg"]
    assert storage.ler("posts/a1/1.jpg") == b"http://x/2"
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_post_sem_nenhuma_imagem_baixada_e_salvo(session):
    lote = _lote(session)

    def baixar(url):
        raise OSError("boom")

    assert _rodar(session, lote, FakeColetor([_post("a1")]), baixar=baixar) == 1
    assert session.scalars(select(Post)).one().imagens == []


def test_ultima_coleta_atualizada_so_para_perfis_sem_erro(session):
    lote = _lote(session, perfis=("ok", "vazio", "ruim"))
    coletor = FakeColetor([_post("a1", "ok")], erros={"ruim": "algo estranho"})
    _rodar(session, lote, coletor)
    assert _perfil(session, "ok").ultima_coleta_em == AGORA
    assert _perfil(session, "vazio").ultima_coleta_em == AGORA
    assert _perfil(session, "ruim").ultima_coleta_em is None


def test_lote_registra_posts_posts_novos_custo_run_ids_e_concluido(session):
    lote = _lote(session)
    session.add(Post(perfil_id=_perfil(session, "casa").id, shortcode="velho"))
    session.flush()

    class ColetorComRuns(FakeColetor):
        def coletar(self, usernames, *, janela, limite):
            r = super().coletar(usernames, janela=janela, limite=limite)
            return ResultadoLote(posts=r.posts, erros=r.erros, run_ids=["run1"])

    coletor = ColetorComRuns([_post("velho"), _post("n1"), _post("n2")])
    assert _rodar(session, lote, coletor) == 2
    assert lote.status == "concluido"
    assert lote.concluido_em == AGORA
    assert lote.posts == 3
    assert lote.posts_novos == 2
    assert lote.custo_estimado == Decimal("0.0051")
    assert lote.run_ids == ["run1"]


def test_perfil_fora_de_grupos_ainda_e_coletado(session):
    lote = _lote(session)  # Perfil sem grupo e sem fixo
    assert _rodar(session, lote, FakeColetor([_post("a1")])) == 1


def test_username_sem_perfil_e_pulado_com_warning(session, caplog):
    lote = _lote(session, perfis=("casa",))
    lote.perfis = ["casa", "fantasma"]
    coletor = FakeColetor([])
    with caplog.at_level(logging.WARNING):
        _rodar(session, lote, coletor)
    assert any("fantasma" in r.getMessage() for r in caplog.records)
    assert lote.status == "concluido"


def test_lote_concluido_nao_e_reprocessado(session):
    lote = _lote(session, status="concluido")
    coletor = FakeColetor([_post("a1")])
    assert _rodar(session, lote, coletor) == 0
    assert coletor.chamadas == []


def test_falha_do_coletor_propaga(session):
    lote = _lote(session)

    class Quebrado:
        def coletar(self, usernames, *, janela, limite):
            raise RuntimeError("apify caiu")

    with pytest.raises(RuntimeError):
        _rodar(session, lote, Quebrado())
    assert lote.status == "executando"
