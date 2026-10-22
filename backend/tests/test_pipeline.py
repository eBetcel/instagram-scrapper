"""Pipeline de ponta a ponta: extrair_post -> reconciliar_post.

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

from agenda.coleta.apify import ApifyRecusou, ExecucaoFalhou
from agenda.coleta.base import FakeColetor, PostColetado
from agenda.extracao.extrator import FakeExtrator, RespostaInvalida, Resultado, Uso
from agenda.extracao.regras import FUSO
from agenda.extracao.schema import ExtracaoPost
from agenda.jobs import enfileirar
from agenda.models import (
    Evento, EventoFonte, Grupo, GrupoPerfil, Job, LoteColeta, Perfil, Post, Usuario,
)
from agenda.pipeline import Dependencias, tratar_reconciliar_post
from agenda.reconciliacao.decisao import Decisao, FakeReconciliador
from agenda.storage import MemoriaStorage
from agenda.worker import rodar_worker

AGORA = datetime.now(UTC)
HOJE = AGORA.astimezone(FUSO).date()
TODOS = ["extrair_post", "reconciliar_post"]
TABELAS = (
    "revisoes_evento, evento_fontes, eventos, posts, grupo_perfis, grupos, usuarios, perfis, "
    "lotes_coleta, jobs"
)

NOVO = Decisao(decisao="NOVO", evento_id=None, mudancas=[], motivo="novo")


def show(titulo="Show da Banda X", dias=10, **kw):
    base = {
        "titulo": titulo, "data_inicio": HOJE + timedelta(days=dias),
        "local_nome": "Casa Azul", "artistas": ["Banda X"], "cidade": "São Paulo",
    }
    base.update(kw)
    return extraido(**base)


class PrimeiroCandidato:
    """Reconciliador falso: DUPLICADO do primeiro candidato, NOVO sem candidatos."""

    def decidir(self, e, candidatos, post, **kw):
        if candidatos:
            return Decisao(decisao="DUPLICADO", evento_id=candidatos[0].id, mudancas=[],
                           motivo="mesmo show"), None
        return NOVO, None


def deps(extrator=None, reconciliador=None, storage=None, **kw):
    return Dependencias(
        storage=storage or MemoriaStorage(),
        extrator=extrator or FakeExtrator({}),
        reconciliador=reconciliador or FakeReconciliador([]),
        **({"coletor": FakeColetor([])} | kw),
    )


@pytest.fixture
def fabrica(engine):
    def limpar():
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {TABELAS} RESTART IDENTITY CASCADE"))

    limpar()
    yield sessionmaker(engine, expire_on_commit=False)
    limpar()


def criar_posts(fabrica, *pares, storage=None, imgs=0):
    """Posts recém-coletados, como a coleta os deixa: `pendente`, imagens no storage e
    `extrair_post` enfileirado. `pares`: (username, shortcode)."""
    with fabrica.begin() as s:
        for username, sc in pares:
            perfil = s.scalars(select(Perfil).where(Perfil.username == username)).one_or_none()
            if perfil is None:
                perfil = Perfil(fixo=True, username=username)
                s.add(perfil)
                s.flush()
            chaves = [f"posts/{sc}/{n}.jpg" for n in range(imgs)]
            for chave in chaves:
                storage.salvar(chave, b"img:" + chave.encode(), "image/jpeg")
            post = Post(perfil_id=perfil.id, shortcode=sc, legenda=f"legenda {sc}",
                        publicado_em=AGORA - timedelta(hours=2), imagens=chaves, status="pendente")
            s.add(post)
            s.flush()
            enfileirar(s, "extrair_post", {"post_id": post.id}, chave=f"extrair:{post.id}")


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


class ExtratorEspiao(FakeExtrator):
    def extrair(self, legenda, imagens, username, publicado_em):
        self.imagens = imagens
        return super().extrair(legenda, imagens, username, publicado_em)


def test_fluxo_completo_do_post_ao_evento(fabrica):
    storage = MemoriaStorage()
    criar_posts(fabrica, ("casa", "P1"), storage=storage, imgs=2)
    extrator = ExtratorEspiao({"casa": ExtracaoPost(eventos=[show()])})
    d = deps(
        extrator=extrator,
        reconciliador=FakeReconciliador([NOVO]),
        storage=storage,
    )

    assert rodar(fabrica, d) == 2

    [p] = os_posts(fabrica)
    assert p.status == "reconciliado"
    assert extrator.imagens == [b"img:posts/P1/0.jpg", b"img:posts/P1/1.jpg"]
    assert p.extracao["eventos"][0]["titulo"] == "Show da Banda X"
    [ev] = os_eventos(fabrica)
    assert ev.titulo == "Show da Banda X"
    assert ev.local_nome == "Casa Azul"
    assert contar(fabrica, EventoFonte, EventoFonte.post_id == p.id,
                  EventoFonte.decisao == "novo") == 1
    assert contar(fabrica, Job, Job.status != "concluido") == 0
    with fabrica() as s:
        chaves = set(s.scalars(select(Job.chave)))
    assert chaves == {f"extrair:{p.id}", f"reconciliar:{p.id}"}


def test_dois_posts_do_mesmo_show_geram_um_evento_com_duas_fontes(fabrica):
    # PrimeiroCandidato: NOVO no primeiro post; no segundo, buscar_candidatos
    # precisa achar o evento criado, e a decisão é DUPLICADO dele.
    criar_posts(fabrica, ("casa", "P1"), ("produtora", "P2"))
    d = deps(
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
    criar_posts(fabrica, ("casa", "P1"))
    eventos = [
        show(titulo="Samba de Roda", dias=5, artistas=["Grupo A"], local_nome="Bar Um"),
        show(titulo="Noite de Jazz", dias=6, artistas=["Trio B"], local_nome="Clube Dois"),
        show(titulo="Exposição de Gravuras", dias=7, artistas=[], local_nome="Galeria Tres",
             categoria="exposicao"),
        show(titulo="Show Antigo", dias=-3),  # data passada: descartado
        show(titulo=None),  # sem título: descartado
    ]
    d = deps(
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
    criar_posts(fabrica, ("casa", "P1"))
    d = deps()  # FakeExtrator devolve []

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
    criar_posts(fabrica, ("casa", "P1"))
    extrator = ExtratorQuebrado(ConnectionError("openai fora do ar"))
    d = deps(extrator=extrator)

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
    criar_posts(fabrica, ("casa", "P1"))
    d = deps(
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

    def decidir(self, e, candidatos, post, **kw):
        return NOVO, self.uso


def test_custo_e_tokens_gravados_no_post(fabrica):
    criar_posts(fabrica, ("casa", "P1"))
    d = deps(
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
    criar_posts(fabrica, ("casa", "P1"))
    uso = Uso(300, 40, Decimal("0.000184"), "gpt-4.1-mini")
    extrator = ExtratorQuebrado(RespostaInvalida("resposta inválida após 2 tentativas", uso))
    d = deps(extrator=extrator)

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

    def decidir(self, e, candidatos, post, **kw):
        self.chamadas += 1
        if self.chamadas == 2:
            raise ConnectionError("caiu no segundo evento")
        return NOVO, None


def test_falha_no_segundo_evento_desfaz_o_primeiro(fabrica):
    criar_posts(fabrica, ("casa", "P1"))
    d = deps(
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


# --- coleta em lote -----------------------------------------------------------

COLETA = ["coletar_lote", "extrair_post"]


def perfil_novo_em_grupo(fabrica, username="casa"):
    with fabrica.begin() as s:
        u = Usuario(email="dono@x", nome="Dono")
        s.add(u)
        s.flush()
        g = Grupo(dono_id=u.id, nome="g", slug="g")
        p = Perfil(username=username)
        s.add_all([g, p])
        s.flush()
        s.add(GrupoPerfil(grupo_id=g.id, perfil_id=p.id))


def os_lotes(fabrica):
    with fabrica() as s:
        return s.scalars(select(LoteColeta).order_by(LoteColeta.id)).all()


def test_fluxo_do_lote_a_reconciliacao(fabrica, caplog):
    perfil_novo_em_grupo(fabrica)
    coletor = FakeColetor([PostColetado(
        shortcode="L1", legenda="show sexta", publicado_em=AGORA - timedelta(hours=3),
        urls_imagens=["http://x/0.jpg"], perfil="casa",
    )])
    storage = MemoriaStorage()
    d = deps(
        extrator=FakeExtrator({"casa": ExtracaoPost(eventos=[show()])}),
        reconciliador=FakeReconciliador([NOVO]),
        storage=storage, coletor=coletor, baixar=lambda url: b"img",
    )

    with caplog.at_level(logging.INFO, logger="agenda.worker"):
        assert rodar(fabrica, d, COLETA) == 2  # coletar_lote + extrair_post
    [lote] = os_lotes(fabrica)
    assert (lote.tipo, lote.status, lote.janela, lote.limite) == ("novos", "concluido", "30 days", 50)
    assert lote.perfis == ["casa"]
    assert lote.posts_novos == 1
    assert coletor.chamadas == [(["casa"], "30 days", 50)]
    assert any(f"[{lote.id}]" in r.getMessage() for r in caplog.records)
    assert storage.ler("posts/L1/0.jpg") == b"img"

    assert rodar(fabrica, d, ["reconciliar_post"]) == 1
    [p] = os_posts(fabrica)
    assert p.status == "reconciliado"
    [e] = os_eventos(fabrica)
    assert e.titulo == "Show da Banda X"
    assert contar(fabrica, EventoFonte) == 1
    with fabrica() as s:
        assert s.scalars(select(Perfil)).one().ultima_coleta_em is not None


class ColetorQuebrado:
    def __init__(self, exc):
        self.exc = exc
        self.chamadas = 0

    def coletar(self, usernames, *, janela, limite):
        self.chamadas += 1
        raise self.exc


def test_apify_recusou_e_definitivo(fabrica, caplog):
    perfil_novo_em_grupo(fabrica)
    coletor = ColetorQuebrado(ApifyRecusou("Apify recusou POST /v2/acts/x/runs: HTTP 402"))
    with caplog.at_level(logging.ERROR, logger="agenda.worker"):
        rodar(fabrica, deps(coletor=coletor), COLETA)
    assert coletor.chamadas == 1
    with fabrica() as s:
        job = s.scalars(select(Job).where(Job.tipo == "coletar_lote")).one()
    assert (job.status, job.tentativas) == ("erro", 1)
    [lote] = os_lotes(fabrica)
    assert lote.status == "erro"
    assert "HTTP 402" in lote.erro_msg
    assert lote.concluido_em is not None
    assert [r for r in caplog.records if r.levelno == logging.ERROR and "402" in r.getMessage()]


def test_execucao_falhou_repete_e_marca_lote_erro_ao_esgotar(fabrica, caplog):
    perfil_novo_em_grupo(fabrica)
    coletor = ColetorQuebrado(ExecucaoFalhou("execução r1 terminou com FAILED"))
    d = deps(coletor=coletor)
    rodar(fabrica, d, COLETA)
    with fabrica() as s:
        job = s.scalars(select(Job).where(Job.tipo == "coletar_lote")).one()
    assert (job.status, job.tentativas) == ("pendente", 1)
    [lote] = os_lotes(fabrica)
    assert lote.status == "pendente"

    with caplog.at_level(logging.ERROR, logger="agenda.worker"):
        for _ in range(4):
            reagendar_jobs(fabrica)
            rodar(fabrica, d, COLETA)
    assert coletor.chamadas == 5
    with fabrica() as s:
        job = s.scalars(select(Job).where(Job.tipo == "coletar_lote")).one()
    assert (job.status, job.tentativas) == ("erro", 5)
    [lote] = os_lotes(fabrica)  # nenhum lote de novos novo: o em erro bloqueia por 1 h
    assert lote.status == "erro"
    assert "FAILED" in lote.erro_msg
    assert lote.concluido_em is not None
    assert [r for r in caplog.records if r.levelno == logging.ERROR]


# --- worker: agendamento e recuperação (R12, R14) ------------------------------


def test_worker_recupera_job_travado_ao_iniciar(fabrica):
    criar_posts(fabrica, ("casa", "P1"))
    with fabrica.begin() as s:
        s.execute(update(Job).values(status="executando", executar_em=func.now() - timedelta(hours=1)))

    assert rodar(fabrica, deps(), ["extrair_post"]) == 1
    assert contar(fabrica, Job, Job.tipo == "extrair_post", Job.status == "concluido") == 1
    assert os_posts(fabrica)[0].status == "extraido"


def test_worker_ocioso_dorme_e_volta_a_procurar(fabrica):
    criar_posts(fabrica, ("casa", "P1"))
    dormidas = []

    def sleep(segundos):
        dormidas.append(segundos)
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        rodar_worker(deps(), ["extrair_post"], session_factory=fabrica, sleep=sleep,
                     intervalo_ocioso=2.5)
    assert dormidas == [2.5]
    assert contar(fabrica, Job, Job.status == "concluido") == 1


# --- handler ----------------------------------------------------------------


def test_tratar_reconciliar_post_ignora_post_ja_reconciliado(session):
    perfil = Perfil(fixo=True, username="casa")
    session.add(perfil)
    session.flush()
    p = Post(perfil_id=perfil.id, shortcode="P1", status="reconciliado",
             extracao=ExtracaoPost(eventos=[show()]).model_dump(mode="json"))
    session.add(p)
    session.flush()
    job = enfileirar(session, "reconciliar_post", {"post_id": p.id})

    tratar_reconciliar_post(session, job, deps())  # FakeReconciliador vazio: não é chamado

    assert session.scalar(select(func.count()).select_from(Evento)) == 0


# --- revisão final: tipo desconhecido -----------------------------------------


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
    criar_posts(fabrica, ("mada", "M1"))
    lineup = [
        show("Show do Zeca", dias=3, festival="Festival MADA 2026", artistas=["Zeca Pagodinho"]),
        show("Baile com Belisa", dias=3, festival="Festival MADA 2026", artistas=["Belisa"]),
        show("Show do Emicida", dias=4, festival="Festival MADA 2026", artistas=["Emicida"]),
    ]
    d = deps(
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



class Registrador:
    """Reconciliador falso que registra o que recebeu e responde DUPLICADO do primeiro."""

    def __init__(self):
        self.chamadas = []

    def decidir(self, e, candidatos, post, *, exigir_candidato=False):
        self.chamadas.append(([c.id for c in candidatos], exigir_candidato))
        return Decisao(decisao="DUPLICADO", evento_id=candidatos[0].id, mudancas=[], motivo="m"), None


def test_par_forte_de_outro_post_vai_sozinho_e_exige_candidato(session):
    perfil = Perfil(fixo=True, username="dosol")
    session.add(perfil)
    session.flush()
    dia = HOJE + timedelta(days=20)
    antigo = Post(perfil_id=perfil.id, shortcode="A", status="reconciliado")
    session.add(antigo)
    session.flush()
    alvo = Evento(titulo="Festival Dosol 2026 na Sede Cultural Dosol", categoria="festival",
                  inicio=datetime.combine(dia, datetime.min.time(), tzinfo=FUSO), hora_definida=False)
    outro = Evento(titulo="Festival Dosol 2026", categoria="festival",
                   inicio=datetime.combine(dia - timedelta(days=1), datetime.min.time(), tzinfo=FUSO),
                   hora_definida=False)
    session.add_all([alvo, outro])
    session.flush()
    session.add(EventoFonte(evento_id=alvo.id, post_id=antigo.id, decisao="novo"))
    novo = Post(perfil_id=perfil.id, shortcode="B", status="extraido", extracao=ExtracaoPost(eventos=[
        show("Festival Dosol 2026", dias=20, local_nome="Sede Dosol", artistas=[], cidade=None)
    ]).model_dump(mode="json"))
    session.add(novo)
    session.flush()
    job = enfileirar(session, "reconciliar_post", {"post_id": novo.id})
    reg = Registrador()

    tratar_reconciliar_post(session, job, deps(reconciliador=reg))

    assert reg.chamadas == [([alvo.id], True)]
    assert session.scalar(select(func.count()).select_from(Evento)) == 2


def test_fim_da_reconciliacao_funde_duplicatas_do_dia_tocado(session):
    perfil = Perfil(fixo=True, username="casa")
    session.add(perfil)
    session.flush()
    dia = HOJE + timedelta(days=15)
    inicio = datetime.combine(dia, datetime.min.time(), tzinfo=FUSO)
    session.add_all([
        Evento(titulo="Festival Dosol 2026", categoria="festival", inicio=inicio, hora_definida=False),
        Evento(titulo="Festival Dosol 2026 na Sede", categoria="festival", inicio=inicio, hora_definida=False),
    ])
    p = Post(perfil_id=perfil.id, shortcode="P1", status="extraido", extracao=ExtracaoPost(
        eventos=[show("Oficina de Cerâmica", dias=15, artistas=[])]).model_dump(mode="json"))
    session.add(p)
    session.flush()
    job = enfileirar(session, "reconciliar_post", {"post_id": p.id})

    tratar_reconciliar_post(session, job, deps(reconciliador=FakeReconciliador([NOVO])))

    titulos = sorted(session.scalars(select(Evento.titulo)))
    assert len(titulos) == 2 and "Oficina de Cerâmica" in titulos
