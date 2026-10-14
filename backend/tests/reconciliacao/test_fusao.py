from datetime import datetime, timedelta

from fabricas import AGORA, evento, post
from sqlalchemy import func, select

from agenda.extracao.regras import FUSO
from agenda.models import Evento, EventoFonte, RevisaoEvento
from agenda.reconciliacao.fusao import deduplicar, fundir

DIA = datetime(2026, 12, 5, tzinfo=FUSO)


def _fonte(s, ev, p, decisao="novo"):
    s.add(EventoFonte(evento_id=ev.id, post_id=p.id, decisao=decisao))
    s.flush()


def _fontes(s, ev):
    return sorted(s.scalars(select(EventoFonte.post_id).where(EventoFonte.evento_id == ev.id)))


def _existe(s, ev_id):
    return s.get(Evento, ev_id) is not None


def test_fundir_move_fontes_e_descarta_fonte_repetida(session):
    manter, remover = evento(session, "Festival", DIA), evento(session, "Festival 2026", DIA)
    p1, p2 = post(session, "P1"), post(session, "P2")
    _fonte(session, manter, p1)
    _fonte(session, remover, p1, "duplicado")
    _fonte(session, remover, p2)
    rid = remover.id
    fundir(session, manter, remover, "fusão")
    assert _fontes(session, manter) == [p1.id, p2.id]
    assert not _existe(session, rid)


def test_fundir_move_revisoes(session):
    manter, remover = evento(session, "Festival", DIA), evento(session, "Festival 2026", DIA)
    session.add(RevisaoEvento(evento_id=remover.id, campo="preco_min", valor_novo="10"))
    session.flush()
    fundir(session, manter, remover, "fusão")
    revs = list(session.scalars(select(RevisaoEvento).where(RevisaoEvento.campo == "preco_min")))
    assert [r.evento_id for r in revs] == [manter.id]


def test_fundir_preenche_vazios_com_revisao_e_acrescenta_hora(session):
    manter = evento(session, "Festival", DIA, hora_definida=False)
    remover = evento(session, "Festival 2026", DIA.replace(hour=16), hora_definida=True,
                     link_ingresso="https://x", cidade="Natal")
    fundir(session, manter, remover, "fusão de duplicata")
    assert (manter.link_ingresso, manter.cidade) == ("https://x", "Natal")
    assert manter.inicio == DIA.replace(hour=16) and manter.hora_definida
    motivos = {r.campo: r.motivo for r in session.scalars(
        select(RevisaoEvento).where(RevisaoEvento.evento_id == manter.id))}
    assert motivos["link_ingresso"] == "fusão de duplicata" and "inicio" in motivos


def test_fundir_nao_sobrescreve_preenchido(session):
    manter = evento(session, "Festival", DIA, cidade="Natal")
    remover = evento(session, "Festival 2026", DIA, cidade="Macaíba")
    fundir(session, manter, remover, "fusão")
    assert manter.cidade == "Natal"


def test_fundir_une_artistas(session):
    manter = evento(session, "Festival", DIA, artistas=["Siba", "Vanguart"])
    remover = evento(session, "Festival 2026", DIA, artistas=["siba", "Marti"])
    fundir(session, manter, remover, "fusão")
    assert manter.artistas == ["Siba", "Vanguart", "Marti"]
    assert manter.artistas_norm == ["siba", "vanguart", "marti"]


def test_fundir_status_ativo_herda_o_do_outro(session):
    manter = evento(session, "Festival", DIA)
    remover = evento(session, "Festival 2026", DIA, status="esgotado")
    fundir(session, manter, remover, "fusão")
    assert manter.status == "esgotado"
    cancelado = evento(session, "Show", DIA, status="cancelado")
    fundir(session, cancelado, evento(session, "Show!", DIA, status="esgotado"), "fusão")
    assert cancelado.status == "cancelado"


def test_deduplicar_funde_cadeia_e_mantem_o_de_mais_fontes(session):
    a = evento(session, "Festival Dosol 2026 na Sede Cultural Dosol", DIA, hora_definida=False)
    b = evento(session, "Festival Dosol 2026", DIA, hora_definida=False)
    c = evento(session, "festival dosol 2026", DIA, hora_definida=False)
    p1, p2 = post(session, "P1"), post(session, "P2")
    _fonte(session, b, p1)
    _fonte(session, b, p2)
    fusoes = deduplicar(session, agora=AGORA)
    assert sorted(fusoes) == sorted([(b.id, a.id), (b.id, c.id)])
    assert session.scalar(select(func.count()).select_from(Evento)) == 1


def test_deduplicar_ignora_outro_dia_e_passado_distante(session):
    evento(session, "Festival Dosol 2026", DIA, hora_definida=False)
    evento(session, "Festival Dosol 2026", DIA + timedelta(days=1), hora_definida=False)
    velho = AGORA - timedelta(days=10)
    evento(session, "Show Antigo", velho)
    evento(session, "Show Antigo", velho)
    assert deduplicar(session, agora=AGORA) == []


def test_deduplicar_so_os_dias_dos_eventos_dados(session):
    a = evento(session, "Festival Dosol 2026", DIA, hora_definida=False)
    evento(session, "Festival Dosol 2026", DIA, hora_definida=False)
    outro_dia = DIA + timedelta(days=3)
    x = evento(session, "Jazz", outro_dia, hora_definida=False)
    evento(session, "Jazz no Bar", outro_dia, hora_definida=False)
    fusoes = deduplicar(session, agora=AGORA, eventos=[x])
    assert len(fusoes) == 1 and _existe(session, a.id)
    assert session.scalar(select(func.count()).select_from(Evento)) == 3
