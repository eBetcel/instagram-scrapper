"""Pipeline de ponta a ponta: coletar_perfil -> extrair_post -> reconciliar_post.

Os testes de worker usam sessões reais (commit) e limpam as tabelas depois.
Datas são relativas ao relógio real, para que o agendamento por `now()` do
Postgres e o `relogio` das Dependencias concordem.
"""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from reconciliacao.fabricas import extraido
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import sessionmaker

from agenda.coleta.base import FakeColetor, PostColetado, SemContasDisponiveis
from agenda.extracao.extrator import FakeExtrator, RespostaInvalida, Resultado, Uso
from agenda.extracao.regras import FUSO
from agenda.extracao.schema import ExtracaoPost
from agenda.jobs import enfileirar
from agenda.models import Evento, EventoFonte, Job, Perfil, Post
from agenda.pipeline import Dependencias, tratar_reconciliar_post
from agenda.reconciliacao.decisao import Decisao, FakeReconciliador
from agenda.storage import MemoriaStorage
from agenda.worker import rodar_worker

AGORA = datetime.now(UTC)
HOJE = AGORA.astimezone(FUSO).date()
TODOS = ["coletar_perfil", "extrair_post", "reconciliar_post"]
TABELAS = "revisoes_evento, evento_fontes, eventos, posts, perfis, jobs, contas_coleta"

NOVO = Decisao(decisao="NOVO", evento_id=None, mudancas=[], motivo="novo")


def baixar(url: str) -> bytes:
    return b"img:" + url.encode()


def show(titulo="Show da Banda X", dias=10, **kw):
    base = {
        "titulo": titulo, "data_inicio": HOJE + timedelta(days=dias),
        "local_nome": "Casa Azul", "artistas": ["Banda X"], "cidade": "São Paulo",
    }
    base.update(kw)
    return extraido(**base)


def postado(sc, imgs=1):
    return PostColetado(
        shortcode=sc, legenda=f"legenda {sc}", publicado_em=AGORA - timedelta(hours=2),
        urls_imagens=[f"http://x/{sc}/{i}" for i in range(imgs)],
    )


class PrimeiroCandidato:
    """Reconciliador falso: DUPLICADO do primeiro candidato, NOVO sem candidatos."""

    def decidir(self, e, candidatos, post):
        if candidatos:
            return Decisao(decisao="DUPLICADO", evento_id=candidatos[0].id, mudancas=[],
                           motivo="mesmo show"), None
        return NOVO, None


def deps(coletor=None, extrator=None, reconciliador=None, storage=None, **kw):
    return Dependencias(
        coletor=coletor or FakeColetor({}),
        storage=storage or MemoriaStorage(),
        extrator=extrator or FakeExtrator({}),
        reconciliador=reconciliador or FakeReconciliador([]),
        baixar=baixar,
        intervalo_coleta_horas=6,
        **kw,
    )


@pytest.fixture
def fabrica(engine):
    def limpar():
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {TABELAS} RESTART IDENTITY CASCADE"))

    limpar()
    yield sessionmaker(engine, expire_on_commit=False)
    limpar()


def criar_perfis(fabrica, *usernames):
    """Perfis com coleta já enfileirada (mesma chave usada pelo agendador)."""
    with fabrica.begin() as s:
        for u in usernames:
            p = Perfil(username=u)
            s.add(p)
            s.flush()
            enfileirar(s, "coletar_perfil", {"perfil_id": p.id}, chave=f"coletar:{p.id}")


def rodar(fabrica, d, tipos=TODOS):
    return rodar_worker(d, tipos, session_factory=fabrica, uma_vez=True, sleep=_sem_sleep)


def _sem_sleep(_):
    raise AssertionError("uma_vez não deveria dormir")


def contar(fabrica, modelo, *where):
    with fabrica() as s:
        return s.scalar(select(func.count()).select_from(modelo).where(*where))


def os_posts(fabrica):
    with fabrica() as s:
        return s.scalars(select(Post).order_by(Post.id)).all()


def os_eventos(fabrica):
    with fabrica() as s:
        return s.scalars(select(Evento).order_by(Evento.id)).all()


def reagendar_jobs(fabrica):
    with fabrica.begin() as s:
        s.execute(update(Job).where(Job.status == "pendente").values(executar_em=func.now()))


# --- ponta a ponta -----------------------------------------------------------


def test_fluxo_completo_do_perfil_ao_evento(fabrica):
    criar_perfis(fabrica, "casa")
    storage = MemoriaStorage()
    d = deps(
        coletor=FakeColetor({"casa": [postado("P1", imgs=2)]}),
        extrator=FakeExtrator({"casa": ExtracaoPost(eventos=[show()])}),
        reconciliador=FakeReconciliador([NOVO]),
        storage=storage,
    )

    assert rodar(fabrica, d) == 3

    [p] = os_posts(fabrica)
    assert p.status == "reconciliado"
    assert p.imagens == ["posts/P1/0.jpg", "posts/P1/1.jpg"]
    assert storage.ler("posts/P1/1.jpg") == b"img:http://x/P1/1"
    assert p.extracao["eventos"][0]["titulo"] == "Show da Banda X"
    [ev] = os_eventos(fabrica)
    assert ev.titulo == "Show da Banda X"
    assert ev.local_nome == "Casa Azul"
    assert contar(fabrica, EventoFonte, EventoFonte.post_id == p.id,
                  EventoFonte.decisao == "novo") == 1
    assert contar(fabrica, Job, Job.status != "concluido") == 0
    with fabrica() as s:
        chaves = set(s.scalars(select(Job.chave)))
    assert chaves == {"coletar:1", f"extrair:{p.id}", f"reconciliar:{p.id}"}


def test_dois_posts_do_mesmo_show_geram_um_evento_com_duas_fontes(fabrica):
    # PrimeiroCandidato: NOVO no primeiro post; no segundo, buscar_candidatos
    # precisa achar o evento criado, e a decisão é DUPLICADO dele.
    criar_perfis(fabrica, "casa", "produtora")
    d = deps(
        coletor=FakeColetor({"casa": [postado("P1")], "produtora": [postado("P2")]}),
        extrator=FakeExtrator({
            "casa": ExtracaoPost(eventos=[show()]),
            "produtora": ExtracaoPost(eventos=[show(titulo="Banda X ao vivo", local_nome=None)]),
        }),
        reconciliador=PrimeiroCandidato(),
    )

    rodar(fabrica, d)

    [ev] = os_eventos(fabrica)
    assert ev.titulo == "Show da Banda X"
    with fabrica() as s:
        fontes = s.execute(
            select(EventoFonte.post_id, EventoFonte.decisao)
            .where(EventoFonte.evento_id == ev.id).order_by(EventoFonte.post_id)
        ).all()
    p1, p2 = os_posts(fabrica)
    assert fontes == [(p1.id, "novo"), (p2.id, "duplicado")]
    assert p1.status == p2.status == "reconciliado"


def test_post_de_flyer_com_varios_eventos_cria_varios_eventos(fabrica):
    criar_perfis(fabrica, "casa")
    eventos = [
        show(titulo="Samba de Roda", dias=5, artistas=["Grupo A"], local_nome="Bar Um"),
        show(titulo="Noite de Jazz", dias=6, artistas=["Trio B"], local_nome="Clube Dois"),
        show(titulo="Exposição de Gravuras", dias=7, artistas=[], local_nome="Galeria Tres",
             categoria="exposicao"),
        show(titulo="Show Antigo", dias=-3),  # data passada: descartado
        show(titulo=None),  # sem título: descartado
    ]
    d = deps(
        coletor=FakeColetor({"casa": [postado("P1")]}),
        extrator=FakeExtrator({"casa": ExtracaoPost(eventos=eventos)}),
        reconciliador=FakeReconciliador([NOVO, NOVO, NOVO]),
    )

    rodar(fabrica, d)

    assert [e.titulo for e in os_eventos(fabrica)] == [
        "Samba de Roda", "Noite de Jazz", "Exposição de Gravuras",
    ]
    assert contar(fabrica, EventoFonte) == 3
    assert os_posts(fabrica)[0].status == "reconciliado"


def test_post_sem_evento_vira_reconciliado_sem_eventos(fabrica):
    criar_perfis(fabrica, "casa")
    d = deps(coletor=FakeColetor({"casa": [postado("P1")]}))  # FakeExtrator devolve []

    rodar(fabrica, d)

    [p] = os_posts(fabrica)
    assert p.status == "reconciliado"
    assert p.extracao == {"eventos": []}
    assert os_eventos(fabrica) == []


class ExtratorQuebrado:
    def __init__(self, erro: Exception):
        self.erro = erro
        self.chamadas = 0

    def extrair(self, legenda, imagens, username, publicado_em):
        self.chamadas += 1
        raise self.erro


def test_erro_da_openai_reagenda_e_depois_marca_post_como_erro(fabrica, caplog):
    criar_perfis(fabrica, "casa")
    extrator = ExtratorQuebrado(ConnectionError("openai fora do ar"))
    d = deps(coletor=FakeColetor({"casa": [postado("P1")]}), extrator=extrator)

    rodar(fabrica, d)

    with fabrica() as s:
        job = s.scalars(select(Job).where(Job.tipo == "extrair_post")).one()
        assert job.status == "pendente"
        assert job.tentativas == 1
        assert job.executar_em > s.scalar(select(func.now()))
    assert os_posts(fabrica)[0].status == "pendente"

    with caplog.at_level(logging.ERROR, logger="agenda.worker"):
        for _ in range(4):
            reagendar_jobs(fabrica)
            rodar(fabrica, d, ["extrair_post"])

    assert extrator.chamadas == 5
    with fabrica() as s:
        job = s.scalars(select(Job).where(Job.tipo == "extrair_post")).one()
    assert job.status == "erro"
    assert job.tentativas == 5
    [p] = os_posts(fabrica)
    assert p.status == "erro"
    assert "openai fora do ar" in p.erro_msg
    assert [r for r in caplog.records if r.levelno == logging.ERROR]


def test_reprocessar_post_reconciliado_nao_duplica(fabrica):
    criar_perfis(fabrica, "casa")
    d = deps(
        coletor=FakeColetor({"casa": [postado("P1")]}),
        extrator=FakeExtrator({"casa": ExtracaoPost(eventos=[show()])}),
        reconciliador=FakeReconciliador([NOVO]),
    )
    rodar(fabrica, d)
    [p] = os_posts(fabrica)

    with fabrica.begin() as s:
        enfileirar(s, "extrair_post", {"post_id": p.id}, chave=f"extrair:{p.id}")
        enfileirar(s, "reconciliar_post", {"post_id": p.id}, chave=f"reconciliar:{p.id}")
    # FakeReconciliador sem decisões: chamá-lo de novo seria IndexError.
    assert rodar(fabrica, d, ["extrair_post", "reconciliar_post"]) == 2

    assert contar(fabrica, Evento) == 1
    assert contar(fabrica, EventoFonte) == 1
    assert contar(fabrica, Job, Job.status != "concluido") == 0
    assert os_posts(fabrica)[0].status == "reconciliado"


class ExtratorComUso:
    def __init__(self, extracao, uso):
        self.extracao = extracao
        self.uso = uso

    def extrair(self, legenda, imagens, username, publicado_em):
        return Resultado(self.extracao, self.uso)


class ReconciliadorComUso:
    def __init__(self, uso):
        self.uso = uso

    def decidir(self, e, candidatos, post):
        return NOVO, self.uso


def test_custo_e_tokens_gravados_no_post(fabrica):
    criar_perfis(fabrica, "casa")
    d = deps(
        coletor=FakeColetor({"casa": [postado("P1")]}),
        extrator=ExtratorComUso(
            ExtracaoPost(eventos=[show(), show(titulo="Outro Show", artistas=["Y"],
                                               local_nome="Outro Lugar")]),
            Uso(100, 20, Decimal("0.000072"), "gpt-4.1-mini"),
        ),
        reconciliador=ReconciliadorComUso(Uso(10, 2, Decimal("0.000002"), "gpt-4.1-nano")),
    )

    rodar(fabrica, d)

    [p] = os_posts(fabrica)
    assert p.status == "reconciliado"
    assert p.tokens_entrada == 120
    assert p.tokens_saida == 24
    assert p.custo_estimado == Decimal("0.000076")
    assert p.modelo_extracao == "gpt-4.1-mini"


# --- R25: resposta inválida é terminal ----------------------------------------


def test_resposta_invalida_marca_erro_sem_retentativa_e_grava_uso(fabrica, caplog):
    criar_perfis(fabrica, "casa")
    uso = Uso(300, 40, Decimal("0.000184"), "gpt-4.1-mini")
    extrator = ExtratorQuebrado(RespostaInvalida("resposta inválida após 2 tentativas", uso))
    d = deps(coletor=FakeColetor({"casa": [postado("P1")]}), extrator=extrator)

    with caplog.at_level(logging.ERROR, logger="agenda.worker"):
        rodar(fabrica, d)

    with fabrica() as s:
        job = s.scalars(select(Job).where(Job.tipo == "extrair_post")).one()
    assert job.status == "erro"
    assert job.tentativas == 1
    assert extrator.chamadas == 1
    [p] = os_posts(fabrica)
    assert p.status == "erro"
    assert "resposta inválida" in p.erro_msg
    assert (p.tokens_entrada, p.tokens_saida, p.custo_estimado) == (300, 40, Decimal("0.000184"))
    assert [r for r in caplog.records if r.levelno == logging.ERROR]


# --- R26: reconciliação atômica por post ---------------------------------------


class FalhaNoSegundo:
    def __init__(self):
        self.chamadas = 0

    def decidir(self, e, candidatos, post):
        self.chamadas += 1
        if self.chamadas == 2:
            raise ConnectionError("caiu no segundo evento")
        return NOVO, None


def test_falha_no_segundo_evento_desfaz_o_primeiro(fabrica):
    criar_perfis(fabrica, "casa")
    d = deps(
        coletor=FakeColetor({"casa": [postado("P1")]}),
        extrator=FakeExtrator({"casa": ExtracaoPost(eventos=[
            show(titulo="Primeiro", artistas=["A"]), show(titulo="Segundo", artistas=["B"]),
        ])}),
        reconciliador=FalhaNoSegundo(),
    )

    rodar(fabrica, d)

    assert contar(fabrica, Evento) == 0
    assert contar(fabrica, EventoFonte) == 0
    [p] = os_posts(fabrica)
    assert p.status == "extraido"
    with fabrica() as s:
        job = s.scalars(select(Job).where(Job.tipo == "reconciliar_post")).one()
    assert job.status == "pendente"
    assert job.tentativas == 1
    assert "caiu no segundo evento" in job.erro_msg


# --- worker: agendamento e recuperação (R12, R14) ------------------------------


def test_worker_de_coleta_agenda_perfis_devidos(fabrica):
    with fabrica.begin() as s:
        s.add(Perfil(username="casa"))
    # perfil nunca coletado: agendado sem jitter, então já roda na mesma passada
    assert rodar(fabrica, deps(), ["coletar_perfil"]) == 1
    with fabrica() as s:
        job = s.scalars(select(Job)).one()
    assert (job.tipo, job.chave, job.status) == ("coletar_perfil", "coletar:1", "concluido")


def test_worker_de_reconciliacao_nao_agenda_coletas(fabrica):
    with fabrica.begin() as s:
        s.add(Perfil(username="casa"))
    rodar(fabrica, deps(), ["reconciliar_post"])
    assert contar(fabrica, Job) == 0


def test_worker_recupera_job_travado_ao_iniciar(fabrica):
    with fabrica.begin() as s:
        p = Perfil(username="casa")
        s.add(p)
        s.flush()
        job = enfileirar(s, "coletar_perfil", {"perfil_id": p.id}, chave=f"coletar:{p.id}")
        job.status = "executando"
        job.executar_em = func.now() - timedelta(hours=1)

    d = deps(coletor=FakeColetor({"casa": [postado("P1")]}))
    assert rodar(fabrica, d, ["coletar_perfil"]) == 1
    assert contar(fabrica, Job, Job.tipo == "coletar_perfil", Job.status == "concluido") == 1
    assert contar(fabrica, Post) == 1


def test_worker_ocioso_dorme_e_volta_a_procurar(fabrica):
    criar_perfis(fabrica, "casa")
    dormidas = []

    def sleep(segundos):
        dormidas.append(segundos)
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        rodar_worker(deps(), ["coletar_perfil"], session_factory=fabrica, sleep=sleep,
                     intervalo_ocioso=2.5)
    assert dormidas == [2.5]
    assert contar(fabrica, Job, Job.status == "concluido") == 1


# --- handler ----------------------------------------------------------------


def test_tratar_reconciliar_post_ignora_post_ja_reconciliado(session):
    perfil = Perfil(username="casa")
    session.add(perfil)
    session.flush()
    p = Post(perfil_id=perfil.id, shortcode="P1", status="reconciliado",
             extracao=ExtracaoPost(eventos=[show()]).model_dump(mode="json"))
    session.add(p)
    session.flush()
    job = enfileirar(session, "reconciliar_post", {"post_id": p.id})

    tratar_reconciliar_post(session, job, deps())  # FakeReconciliador vazio: não é chamado

    assert session.scalar(select(func.count()).select_from(Evento)) == 0


# --- revisão final: sem contas, coleta morta, tipo desconhecido ----------------


@pytest.mark.parametrize("disponivel_em", [AGORA + timedelta(hours=2), None])
def test_sem_contas_adia_coleta_sem_gastar_tentativa(fabrica, disponivel_em):
    criar_perfis(fabrica, "casa")
    erro = SemContasDisponiveis(disponivel_em=disponivel_em)
    d = deps(coletor=FakeColetor({}, erros={"casa": erro}))

    assert rodar(fabrica, d, ["coletar_perfil"]) == 1

    with fabrica() as s:
        job = s.scalars(select(Job).where(Job.tipo == "coletar_perfil")).one()
        agora_db = s.scalar(select(func.now()))
    assert (job.status, job.tentativas) == ("pendente", 0)
    assert "SemContasDisponiveis" in job.erro_msg
    if disponivel_em is not None:
        assert job.executar_em == disponivel_em
    else:
        assert abs((job.executar_em - (agora_db + timedelta(hours=1))).total_seconds()) < 60


def test_coleta_esgotada_empurra_proxima_coleta_do_perfil(fabrica):
    criar_perfis(fabrica, "casa")
    d = deps(coletor=FakeColetor({}, erros={"casa": ConnectionError("rede")}))
    rodar(fabrica, d, ["coletar_perfil"])
    for _ in range(4):
        reagendar_jobs(fabrica)
        rodar(fabrica, d, ["coletar_perfil"])
    with fabrica() as s:
        job = s.scalars(select(Job).where(Job.tipo == "coletar_perfil")).one()
        perfil = s.scalars(select(Perfil)).one()
    assert job.status == "erro"
    # o agendador só reativa o job no próximo intervalo, sem martelar o perfil
    assert perfil.proxima_coleta_em is not None
    assert perfil.proxima_coleta_em > AGORA + timedelta(hours=5)


def test_tipo_de_job_desconhecido_falha_sem_retentativa(fabrica):
    with fabrica.begin() as s:
        enfileirar(s, "tipo_inexistente", {})
    assert rodar(fabrica, deps(), ["tipo_inexistente"]) == 1
    with fabrica() as s:
        job = s.scalars(select(Job)).one()
    assert (job.status, job.tentativas) == ("erro", 1)
    assert "tipo_inexistente" in job.erro_msg


# --- festivais -----------------------------------------------------------------


def test_atracoes_do_festival_viram_um_evento_por_dia(fabrica):
    criar_perfis(fabrica, "mada")
    lineup = [
        show("Show do Zeca", dias=3, festival="Festival MADA 2026", artistas=["Zeca Pagodinho"]),
        show("Baile com Belisa", dias=3, festival="Festival MADA 2026", artistas=["Belisa"]),
        show("Show do Emicida", dias=4, festival="Festival MADA 2026", artistas=["Emicida"]),
    ]
    d = deps(
        coletor=FakeColetor({"mada": [postado("M1")]}),
        extrator=FakeExtrator({"mada": ExtracaoPost(eventos=lineup)}),
        reconciliador=FakeReconciliador([NOVO, NOVO]),
    )

    rodar(fabrica, d)

    eventos = sorted(os_eventos(fabrica), key=lambda e: e.inicio)
    assert [(e.titulo, e.festival, e.categoria) for e in eventos] == [
        ("Festival MADA 2026", "Festival MADA 2026", "festival")
    ] * 2
    assert eventos[0].artistas == ["Zeca Pagodinho", "Belisa"]
    assert eventos[1].artistas == ["Emicida"]
