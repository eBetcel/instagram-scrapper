from datetime import date, datetime, time
from decimal import Decimal

import pytest
from fabricas import evento, extraido, post
from sqlalchemy import func, select

from agenda.extracao.regras import FUSO
from agenda.models import Evento, EventoFonte, RevisaoEvento
from agenda.reconciliacao import aplicar as aplicar_mod
from agenda.reconciliacao.aplicar import DecisaoInvalida, aplicar, campos_do_evento
from agenda.reconciliacao.decisao import Decisao

E = extraido(
    titulo="Festival Jazz na Praça", descricao="Jazz ao ar livre",
    data_inicio=date(2026, 11, 20), hora_inicio=time(20, 0),
    local_nome="Praça Central", cidade="Belo Horizonte", categoria="festival",
    preco_texto="R$ 20 a R$ 40", preco_min=20.0, preco_max=40.0,
    link_ingresso="https://ingressos.example/jazz", artistas=["Fulano", "Beltrana"],
)
INICIO = datetime(2026, 11, 20, 20, 0, tzinfo=FUSO)


def _d(decisao="NOVO", evento_id=None, mudancas=(), motivo="motivo do modelo"):
    return Decisao(decisao=decisao, evento_id=evento_id, mudancas=list(mudancas), motivo=motivo)


def _n(s, modelo) -> int:
    return s.scalar(select(func.count()).select_from(modelo))


def _fontes(s, ev):
    return list(s.scalars(select(EventoFonte).where(EventoFonte.evento_id == ev.id)))


def _revisoes(s, ev):
    stmt = select(RevisaoEvento).where(RevisaoEvento.evento_id == ev.id).order_by(RevisaoEvento.id)
    return list(s.scalars(stmt))


# --- campos_do_evento ---------------------------------------------------------


def test_campos_do_evento_mapeia_tudo():
    c = campos_do_evento(E)
    assert c["titulo"] == "Festival Jazz na Praça"
    assert c["inicio"] == INICIO and c["hora_definida"] is True
    assert c["fim"] is None
    assert c["preco_min"] == Decimal("20") and isinstance(c["preco_min"], Decimal)
    assert c["preco_max"] == Decimal("40") and isinstance(c["preco_max"], Decimal)
    assert c["artistas"] == ["Fulano", "Beltrana"]
    assert c["artistas_norm"] == ["fulano", "beltrana"]
    assert c["status"] == "ativo"
    assert c["categoria"] == "festival"


def test_campos_do_evento_preco_decimal_exato():
    c = campos_do_evento(extraido(titulo="x", data_inicio=date(2026, 11, 1), preco_min=19.9))
    assert c["preco_min"] == Decimal("19.9")
    assert c["preco_max"] is None


def test_campos_do_evento_sem_hora():
    c = campos_do_evento(extraido(titulo="x", data_inicio=date(2026, 11, 1), data_fim=date(2026, 11, 3)))
    assert c["inicio"] == datetime(2026, 11, 1, 0, 0, tzinfo=FUSO)
    assert c["hora_definida"] is False
    assert c["fim"] == datetime(2026, 11, 3, 23, 59, tzinfo=FUSO)


def test_campos_do_evento_gratuito_e_status():
    c = campos_do_evento(
        extraido(titulo="x", data_inicio=date(2026, 11, 1), gratuito=True, status_indicado="esgotado")
    )
    assert c["preco_min"] == Decimal(0) and c["preco_max"] == Decimal(0)
    assert c["status"] == "esgotado"


def test_campos_do_evento_artistas_norm():
    c = campos_do_evento(extraido(titulo="x", data_inicio=date(2026, 11, 1), artistas=[" Jão", "JAO"]))
    assert c["artistas"] == [" Jão", "JAO"]
    assert c["artistas_norm"] == ["jao"]


# --- NOVO ---------------------------------------------------------------------


def test_novo_cria_evento_e_fonte(session):
    p = post(session)
    ev = aplicar(session, E, _d("NOVO"), [], p)
    session.refresh(ev)
    assert ev.id is not None
    assert ev.titulo == "Festival Jazz na Praça"
    assert ev.inicio == INICIO
    assert ev.preco_min == Decimal("20.00")
    assert ev.artistas_norm == ["fulano", "beltrana"]
    assert ev.status == "ativo"
    [f] = _fontes(session, ev)
    assert (f.post_id, f.decisao) == (p.id, "novo")
    assert _revisoes(session, ev) == []


def test_novo_ignora_evento_id(session):
    ev = aplicar(session, E, _d("NOVO", evento_id=99999), [], post(session))
    assert ev.id != 99999


def test_reaplicar_novo_do_mesmo_post_nao_cria_outro_evento(session):
    p = post(session)
    ev = aplicar(session, E, _d("NOVO"), [], p)
    de_novo = aplicar(session, E, _d("NOVO"), [ev], p)
    assert de_novo.id == ev.id
    assert _n(session, Evento) == 1
    assert len(_fontes(session, ev)) == 1


def test_agenda_mensal_mesmo_post_titulo_parecido_inicio_diferente_cria_outro(session):
    p = post(session)
    primeiro = aplicar(session, E, _d("NOVO"), [], p)
    outra_data = E.model_copy(update={"data_inicio": date(2026, 11, 27)})
    segundo = aplicar(session, outra_data, _d("NOVO"), [primeiro], p)
    assert segundo.id != primeiro.id
    assert _n(session, Evento) == 2
    assert [f.decisao for f in _fontes(session, segundo)] == ["novo"]


# --- DUPLICADO ----------------------------------------------------------------


def test_duplicado_so_vincula_fonte(session):
    ev = evento(
        session, "Festival Jazz na Praça", INICIO, descricao="d", local_nome="Praça",
        endereco="Rua A", cidade="BH", preco_texto="R$ 30", gratuito=False,
        preco_min=Decimal(30), preco_max=Decimal(30), link_ingresso="https://a",
        artistas=["Ciclano"],
    )
    p = post(session)
    r = aplicar(session, E, _d("DUPLICADO", ev.id), [ev], p)
    assert r.id == ev.id
    assert ev.titulo == "Festival Jazz na Praça" and ev.link_ingresso == "https://a"
    assert ev.artistas == ["Ciclano"]
    [f] = _fontes(session, ev)
    assert (f.post_id, f.decisao) == (p.id, "duplicado")
    assert _revisoes(session, ev) == []
    assert _n(session, Evento) == 1


def test_duplicado_preenche_link_ingresso_nulo_e_registra_revisao(session):
    ev = evento(
        session, "Festival Jazz na Praça", INICIO, descricao="d", local_nome="Praça",
        endereco="Rua A", cidade="BH", preco_texto="R$ 30", gratuito=False,
        preco_min=Decimal(30), preco_max=Decimal(30), artistas=["Ciclano"],
    )
    p = post(session)
    aplicar(session, E, _d("DUPLICADO", ev.id, motivo="mesmo show"), [ev], p)
    assert ev.link_ingresso == "https://ingressos.example/jazz"
    [r] = _revisoes(session, ev)
    assert (r.campo, r.valor_anterior, r.valor_novo) == (
        "link_ingresso", None, "https://ingressos.example/jazz",
    )
    assert (r.post_id, r.motivo) == (p.id, "mesmo show")


def test_duplicado_preenche_artistas_vazios_e_artistas_norm(session):
    ev = evento(session, "Festival Jazz na Praça", INICIO, artistas=[])
    aplicar(session, E, _d("DUPLICADO", ev.id), [ev], post(session))
    assert ev.artistas == ["Fulano", "Beltrana"]
    assert ev.artistas_norm == ["fulano", "beltrana"]
    campos = [r.campo for r in _revisoes(session, ev)]
    assert "artistas" in campos and "artistas_norm" not in campos
    [rev] = [r for r in _revisoes(session, ev) if r.campo == "artistas"]
    assert rev.valor_novo == '["Fulano", "Beltrana"]'


def test_reprocessar_mesmo_post_nao_duplica_fonte(session):
    ev = evento(session, "Festival Jazz na Praça", INICIO)
    p = post(session)
    aplicar(session, E, _d("DUPLICADO", ev.id), [ev], p)
    n_rev = len(_revisoes(session, ev))
    aplicar(session, E, _d("DUPLICADO", ev.id), [ev], p)
    assert len(_fontes(session, ev)) == 1
    assert len(_revisoes(session, ev)) == n_rev


# --- ATUALIZACAO --------------------------------------------------------------


def test_atualizacao_registra_revisao_por_campo_com_antes_e_depois(session):
    ev = evento(
        session, "Festival Jazz na Praça", INICIO, local_nome="Praça Velha",
        preco_min=Decimal(10), link_ingresso="https://velho",
    )
    p = post(session)
    d = _d("ATUALIZACAO", ev.id, ["local_nome", "preco_min", "link_ingresso"], motivo="mudou")
    r = aplicar(session, E, d, [ev], p)
    assert r.id == ev.id
    assert ev.local_nome == "Praça Central"
    assert ev.preco_min == Decimal(20)
    assert ev.link_ingresso == "https://ingressos.example/jazz"
    revs = {r.campo: r for r in _revisoes(session, ev)}
    assert set(revs) == {"local_nome", "preco_min", "link_ingresso"}
    assert (revs["local_nome"].valor_anterior, revs["local_nome"].valor_novo) == (
        "Praça Velha", "Praça Central",
    )
    assert revs["preco_min"].valor_anterior in ("10", "10.00")
    assert revs["preco_min"].valor_novo == "20.0"
    assert all(x.post_id == p.id and x.motivo == "mudou" for x in revs.values())
    [f] = _fontes(session, ev)
    assert f.decisao == "atualizacao"


def test_adiado_muda_status_e_data(session):
    ev = evento(session, "Festival Jazz na Praça", INICIO)
    adiado = E.model_copy(
        update={"data_inicio": date(2026, 12, 4), "hora_inicio": None, "status_indicado": "adiado"}
    )
    d = _d("ATUALIZACAO", ev.id, ["inicio"], motivo="adiado para dezembro")
    aplicar(session, adiado, d, [ev], post(session))
    assert ev.status == "adiado"
    assert ev.inicio == datetime(2026, 12, 4, 0, 0, tzinfo=FUSO)
    assert ev.hora_definida is False
    revs = {r.campo: r for r in _revisoes(session, ev)}
    assert set(revs) == {"inicio", "status"}
    assert (revs["status"].valor_anterior, revs["status"].valor_novo) == ("ativo", "adiado")
    assert datetime.fromisoformat(revs["inicio"].valor_anterior) == INICIO
    assert datetime.fromisoformat(revs["inicio"].valor_novo) == datetime(2026, 12, 4, tzinfo=FUSO)


def test_atualizacao_com_valor_nulo_nao_apaga(session):
    ev = evento(session, "Festival Jazz na Praça", INICIO, link_ingresso="https://a", endereco="Rua A")
    sem = E.model_copy(update={"link_ingresso": None, "endereco": None})
    aplicar(session, sem, _d("ATUALIZACAO", ev.id, ["link_ingresso", "endereco"]), [ev], post(session))
    assert ev.link_ingresso == "https://a" and ev.endereco == "Rua A"
    # Sem nada a mudar, a ATUALIZACAO vira DUPLICADO: preenche só os campos vazios.
    assert not {r.campo for r in _revisoes(session, ev)} & {"link_ingresso", "endereco"}


def test_atualizacao_campo_igual_nao_gera_revisao(session):
    ev = evento(session, "Festival Jazz na Praça", INICIO, local_nome="Praça Central")
    aplicar(session, E, _d("ATUALIZACAO", ev.id, ["local_nome", "inicio"]), [ev], post(session))
    assert _revisoes(session, ev) == []


def test_atualizacao_status_sem_status_indicado_nao_reativa(session):
    ev = evento(session, "Festival Jazz na Praça", INICIO, status="cancelado")
    aplicar(session, E, _d("ATUALIZACAO", ev.id, ["status"]), [ev], post(session))
    assert ev.status == "cancelado"
    assert _revisoes(session, ev) == []


def test_duplicado_nao_mexe_em_status_sem_status_indicado(session):
    ev = evento(session, "Festival Jazz na Praça", INICIO, status="adiado")
    aplicar(session, E, _d("DUPLICADO", ev.id), [ev], post(session))
    assert ev.status == "adiado"
    assert "status" not in [r.campo for r in _revisoes(session, ev)]


# --- validação e transação ----------------------------------------------------


def test_evento_id_fora_dos_candidatos_levanta(session):
    ev = evento(session, "Festival Jazz na Praça", INICIO)
    outro = evento(session, "Outro", INICIO)
    p = post(session)
    with pytest.raises(DecisaoInvalida):
        aplicar(session, E, _d("DUPLICADO", outro.id), [ev], p)
    with pytest.raises(DecisaoInvalida):
        aplicar(session, E, _d("ATUALIZACAO", None), [ev], p)
    assert _n(session, EventoFonte) == 0


def test_campo_nao_permitido_levanta(session):
    ev = evento(session, "Festival Jazz na Praça", INICIO)
    d = Decisao.model_construct(
        decisao="ATUALIZACAO", evento_id=ev.id, mudancas=["criado_em"], motivo="x"
    )
    with pytest.raises(DecisaoInvalida):
        aplicar(session, E, d, [ev], post(session))
    assert _n(session, RevisaoEvento) == 0 and _n(session, EventoFonte) == 0


def test_falha_no_meio_nao_deixa_efeito_parcial(session, monkeypatch):
    p = post(session)

    def explode(*a, **kw):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(aplicar_mod, "_vincular", explode)
    with pytest.raises(RuntimeError):
        aplicar(session, E, _d("NOVO"), [], p)
    assert _n(session, Evento) == 0
    assert _n(session, EventoFonte) == 0

    ev = evento(session, "Festival Jazz na Praça", INICIO)
    with pytest.raises(RuntimeError):
        aplicar(session, E, _d("ATUALIZACAO", ev.id, ["local_nome", "link_ingresso"]), [ev], p)
    assert _n(session, RevisaoEvento) == 0
    session.refresh(ev)
    assert ev.local_nome is None and ev.link_ingresso is None
    # a sessão externa continua utilizável
    assert session.scalar(select(func.count()).select_from(Evento)) == 1


# --- revisão final: mesmo post (R30) e hora conhecida -------------------------


@pytest.mark.parametrize("decisao", ["ATUALIZACAO", "DUPLICADO"])
def test_agenda_mensal_reconciliador_errado_contra_evento_do_mesmo_post_vira_novo(
    session, caplog, decisao
):
    p = post(session)
    primeiro = aplicar(session, E, _d("NOVO"), [], p)
    outra_data = E.model_copy(update={"data_inicio": date(2026, 11, 27)})
    mudancas = ["inicio"] if decisao == "ATUALIZACAO" else []
    with caplog.at_level("WARNING", logger="agenda.reconciliacao.aplicar"):
        segundo = aplicar(session, outra_data, _d(decisao, primeiro.id, mudancas), [primeiro], p)
    assert segundo.id != primeiro.id
    assert primeiro.inicio == INICIO  # o primeiro evento do flyer não foi remarcado
    assert segundo.inicio == datetime(2026, 11, 27, 20, 0, tzinfo=FUSO)
    assert _revisoes(session, primeiro) == []
    assert [f.decisao for f in _fontes(session, segundo)] == ["novo"]
    assert [r for r in caplog.records if r.levelname == "WARNING"]


def test_atualizacao_de_outro_post_com_outro_inicio_continua_valendo(session):
    ev = evento(session, "Festival Jazz na Praça", INICIO)
    aplicar(session, E, _d("NOVO"), [], post(session, "P0"))  # outro evento, outro post
    nova = E.model_copy(update={"data_inicio": date(2026, 11, 27)})
    alvo = aplicar(session, nova, _d("ATUALIZACAO", ev.id, ["inicio"]), [ev], post(session, "P2"))
    assert alvo.id == ev.id
    assert ev.inicio == datetime(2026, 11, 27, 20, 0, tzinfo=FUSO)


def test_atualizacao_sem_hora_na_mesma_data_nao_apaga_horario(session):
    ev = evento(session, "Festival Jazz na Praça", INICIO, hora_definida=True)
    sem_hora = E.model_copy(update={"hora_inicio": None, "status_indicado": "esgotado"})
    aplicar(session, sem_hora, _d("ATUALIZACAO", ev.id, ["inicio", "status"]), [ev], post(session))
    assert ev.inicio == INICIO
    assert ev.hora_definida is True
    assert ev.status == "esgotado"
    assert {r.campo for r in _revisoes(session, ev)} == {"status"}


# --- ATUALIZACAO que só preenche vazios vira DUPLICADO --------------------------

def test_atualizacao_que_so_preenche_vazios_e_aplicada_como_duplicado(session):
    ev = evento(session, "Festival Jazz na Praça", INICIO, local_nome="Praça Central")
    aplicar(session, E, _d("ATUALIZACAO", ev.id, ["cidade", "link_ingresso"]), [ev], post(session))
    assert ev.cidade == "Belo Horizonte" and ev.link_ingresso == "https://ingressos.example/jazz"
    assert [f.decisao for f in _fontes(session, ev)] == ["duplicado"]


def test_atualizacao_que_so_acrescenta_hora_na_mesma_data_e_duplicado(session):
    sem_hora = datetime(2026, 11, 20, 0, 0, tzinfo=FUSO)
    ev = evento(session, "Festival Jazz na Praça", sem_hora, hora_definida=False)
    aplicar(session, E, _d("ATUALIZACAO", ev.id, ["inicio"]), [ev], post(session))
    assert ev.inicio == INICIO and ev.hora_definida
    assert [f.decisao for f in _fontes(session, ev)] == ["duplicado"]


def test_atualizacao_que_muda_valor_preenchido_continua_atualizacao(session):
    ev = evento(session, "Festival Jazz na Praça", INICIO, cidade="Contagem")
    aplicar(session, E, _d("ATUALIZACAO", ev.id, ["cidade", "link_ingresso"]), [ev], post(session))
    assert ev.cidade == "Belo Horizonte"
    assert [f.decisao for f in _fontes(session, ev)] == ["atualizacao"]


def test_atualizacao_com_status_indicado_continua_atualizacao(session):
    ev = evento(session, "Festival Jazz na Praça", INICIO)
    esgotado = E.model_copy(update={"status_indicado": "esgotado"})
    aplicar(session, esgotado, _d("ATUALIZACAO", ev.id, ["cidade"]), [ev], post(session))
    assert ev.status == "esgotado"
    assert [f.decisao for f in _fontes(session, ev)] == ["atualizacao"]


def test_atualizacao_listando_campo_que_o_post_nao_informa_e_duplicado(session):
    ev = evento(session, "Festival Jazz na Praça", INICIO, cidade="Belo Horizonte")
    sem_cidade = E.model_copy(update={"cidade": None})
    aplicar(session, sem_cidade, _d("ATUALIZACAO", ev.id, ["cidade", "link_ingresso"]), [ev], post(session))
    assert ev.cidade == "Belo Horizonte" and ev.link_ingresso == "https://ingressos.example/jazz"
    assert [f.decisao for f in _fontes(session, ev)] == ["duplicado"]


# --- festival ------------------------------------------------------------------

def test_campos_do_evento_mapeia_festival():
    e = extraido(titulo="Show do Siba", data_inicio=date(2026, 11, 28), festival="Festival DoSol 2026")
    assert campos_do_evento(e)["festival"] == "Festival DoSol 2026"


def test_duplicado_preenche_festival_vazio(session):
    ev = evento(session, "Festival Jazz na Praça", INICIO)
    com_festival = E.model_copy(update={"festival": "Festival Jazz 2026"})
    aplicar(session, com_festival, _d("DUPLICADO", ev.id), [ev], post(session))
    assert ev.festival == "Festival Jazz 2026"


def _festival_dosol(s):
    return evento(s, "Festival DoSol 2026", INICIO, festival="Festival DoSol 2026",
                  categoria="festival", artistas=["Mercenárias", "Vanguart"])


def test_atualizacao_de_festival_une_artistas(session):
    ev = _festival_dosol(session)
    siba = E.model_copy(update={"titulo": "Festival DoSol 2026", "festival": "Festival DoSol 2026",
                                "artistas": ["Siba", "vanguart"]})
    aplicar(session, siba, _d("ATUALIZACAO", ev.id, ["artistas"]), [ev], post(session))
    assert ev.artistas == ["Mercenárias", "Vanguart", "Siba"]
    assert ev.artistas_norm == ["mercenarias", "vanguart", "siba"]


def test_duplicado_de_festival_acrescenta_artistas_novos(session):
    ev = _festival_dosol(session)
    siba = E.model_copy(update={"titulo": "Festival DoSol 2026", "festival": "Festival DoSol 2026",
                                "artistas": ["Siba"]})
    aplicar(session, siba, _d("DUPLICADO", ev.id), [ev], post(session))
    assert ev.artistas == ["Mercenárias", "Vanguart", "Siba"]


def test_atualizacao_fora_de_festival_continua_substituindo_artistas(session):
    ev = evento(session, "Festival Jazz na Praça", INICIO, artistas=["Ciclano"])
    aplicar(session, E, _d("ATUALIZACAO", ev.id, ["artistas"]), [ev], post(session))
    assert ev.artistas == ["Fulano", "Beltrana"]
