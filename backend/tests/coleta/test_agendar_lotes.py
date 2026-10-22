import threading
from datetime import UTC, datetime, time, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import sessionmaker

from agenda.coleta.servico import (
    agendar_lotes,
    criar_lotes_imediatos,
    janela_agendada,
    ultimo_horario,
)
from agenda.config import Settings, parse_horarios
from agenda.extracao.regras import FUSO
from agenda.models import Grupo, GrupoPerfil, Job, LoteColeta, Perfil, Usuario

HORARIOS = [time(8), time(18)]


def sp(dia, hora, minuto=0):
    return datetime(2030, 1, dia, hora, minuto, tzinfo=FUSO)


def _grupo(s, slug):
    u = s.scalar(select(Usuario).where(Usuario.email == "dono@x"))
    if u is None:
        u = Usuario(email="dono@x", nome="Dono")
        s.add(u)
        s.flush()
    g = Grupo(dono_id=u.id, nome="g", slug=slug)
    s.add(g)
    s.flush()
    return g


def _perfil(s, username, *, coletado=True, grupo=True, fixo=False, status="ativo"):
    p = Perfil(
        username=username, fixo=fixo, status=status,
        ultima_coleta_em=sp(1, 0) if coletado else None,
    )
    s.add(p)
    s.flush()
    if grupo:
        s.add(GrupoPerfil(grupo_id=_grupo(s, f"g-{username}").id, perfil_id=p.id))
        s.flush()
    return p


def _lotes(s, tipo=None):
    q = select(LoteColeta).order_by(LoteColeta.id)
    if tipo:
        q = q.where(LoteColeta.tipo == tipo)
    return s.scalars(q).all()


def _jobs(s):
    return s.scalars(select(Job).where(Job.tipo == "coletar_lote").order_by(Job.id)).all()


def test_ultimo_horario_manha_tarde_e_madrugada():
    assert ultimo_horario(sp(2, 7), HORARIOS) == sp(1, 18)
    assert ultimo_horario(sp(2, 9), HORARIOS) == sp(2, 8)
    assert ultimo_horario(sp(2, 19), HORARIOS) == sp(2, 18)
    assert ultimo_horario(sp(2, 8), HORARIOS) == sp(2, 8)
    # agora em UTC: 10:30 UTC = 07:30 em SP -> 18:00 da véspera
    assert ultimo_horario(datetime(2030, 1, 2, 10, 30, tzinfo=UTC), HORARIOS) == sp(1, 18)


def test_janela_agendada():
    agora = sp(2, 18)
    assert janela_agendada(agora - timedelta(hours=10, minutes=20), agora) == "12 hours"
    assert janela_agendada(agora - timedelta(hours=10), agora) == "11 hours"
    assert janela_agendada(None, agora) == "30 days"
    assert janela_agendada(agora - timedelta(hours=719), agora) == "720 hours"
    assert janela_agendada(agora - timedelta(hours=719, minutes=1), agora) == "30 days"
    assert janela_agendada(agora - timedelta(days=90), agora) == "30 days"


def test_sem_agendado_concluido_janela_parte_da_coleta_mais_antiga_do_lote(session):
    # Logo depois do lote de novos (ou na troca para esta versão): não recoleta 30 dias.
    _perfil(session, "a")  # coletado em sp(1, 0)
    b = _perfil(session, "b")
    b.ultima_coleta_em = sp(2, 6)
    session.add(LoteColeta(tipo="agendado", horario=sp(1, 18), janela="x", limite=20,
                           perfis=["a"], status="erro"))
    session.flush()
    [lote_id] = agendar_lotes(session, sp(2, 8, 30), HORARIOS)
    assert session.get(LoteColeta, lote_id).janela == "34 hours"  # 32h30 -> 33 + 1


def test_sem_agendado_concluido_coleta_antiga_limita_a_30_dias(session):
    p = _perfil(session, "a")
    p.ultima_coleta_em = sp(2, 8) - timedelta(days=45)
    session.flush()
    [lote_id] = agendar_lotes(session, sp(2, 8, 30), HORARIOS)
    assert session.get(LoteColeta, lote_id).janela == "30 days"


def test_lote_imediato_de_coletados_tambem_parte_da_coleta_mais_antiga(session):
    _perfil(session, "a")  # coletado em sp(1, 0)
    _perfil(session, "n", coletado=False)
    lotes = criar_lotes_imediatos(
        session, sp(1, 10), [("a", sp(1, 0)), ("n", None)]
    )
    assert [(l.janela, l.perfis) for l in lotes] == [
        ("30 days", ["n"]), ("11 hours", ["a"]),
    ]


def test_parse_horarios():
    assert parse_horarios("08:00, 18:30") == [time(8), time(18, 30)]
    for ruim in ("", "8h", "25:00", "08:00,,18:00"):
        with pytest.raises(ValueError, match="HORARIOS_COLETA"):
            parse_horarios(ruim)


def test_settings_valida_horarios_coleta():
    kw = {"openai_modelo_extracao": "x", "openai_modelo_reconciliacao": "y"}
    assert Settings(**kw).horarios_coleta == "08:00,18:00"
    with pytest.raises(ValueError, match="HORARIOS_COLETA"):
        Settings(horarios_coleta="8h", **kw)


def test_um_lote_por_horario_mesmo_com_varias_passadas(session):
    _perfil(session, "casa")
    ids = agendar_lotes(session, sp(2, 9), HORARIOS)
    assert len(ids) == 1
    for minuto in (5, 10, 55):
        assert agendar_lotes(session, sp(2, 9, minuto), HORARIOS) == []
    [lote] = _lotes(session)
    assert lote.tipo == "agendado"
    assert lote.horario == sp(2, 8)
    assert lote.limite == 20
    [job] = _jobs(session)
    assert job.payload == {"lote_id": lote.id}
    assert job.chave == f"lote:{lote.id}"
    assert job.max_tentativas == 3
    # próximo horário: novo lote
    assert len(agendar_lotes(session, sp(2, 18, 1), HORARIOS)) == 1
    assert [l.horario for l in _lotes(session)] == [sp(2, 8), sp(2, 18)]


def test_pausa_longa_gera_um_so_lote_com_janela_cobrindo_tudo(session):
    _perfil(session, "casa")
    anterior = LoteColeta(
        tipo="agendado", horario=sp(1, 8), janela="30 days", limite=20, perfis=["casa"],
        status="concluido", concluido_em=sp(1, 8, 10),
    )
    session.add(anterior)
    session.flush()
    # worker parado de 1/jan 08:10 até 4/jan 09:00 (5 horários perdidos)
    ids = agendar_lotes(session, sp(4, 9), HORARIOS)
    assert len(ids) == 1
    lote = session.get(LoteColeta, ids[0])
    assert lote.horario == sp(4, 8)
    # 72h50min -> 73 + 1
    assert lote.janela == "74 hours"


def test_janela_parte_do_ultimo_agendado_concluido(session):
    _perfil(session, "casa")
    session.add_all([
        LoteColeta(tipo="agendado", horario=sp(1, 8), janela="x", limite=20, perfis=["casa"],
                   status="concluido", concluido_em=sp(1, 8, 5)),
        LoteColeta(tipo="agendado", horario=sp(1, 18), janela="x", limite=20, perfis=["casa"],
                   status="erro"),
        LoteColeta(tipo="novos", janela="x", limite=50, perfis=["casa"],
                   status="concluido", concluido_em=sp(2, 7)),
    ])
    session.flush()
    [lote_id] = agendar_lotes(session, sp(2, 8, 5), HORARIOS)
    assert session.get(LoteColeta, lote_id).janela == "25 hours"  # 24h exatas + 1


def test_lote_agendado_so_com_perfis_ja_coletados_e_acompanhados(session):
    _perfil(session, "zeta")
    _perfil(session, "alfa")
    _perfil(session, "fixo", grupo=False, fixo=True)
    _perfil(session, "solto", grupo=False)
    _perfil(session, "sumiu", status="inexistente")
    _perfil(session, "novo", coletado=False)
    agendar_lotes(session, sp(2, 9), HORARIOS)
    [agendado] = _lotes(session, "agendado")
    assert agendado.perfis == ["alfa", "fixo", "zeta"]
    [novos] = _lotes(session, "novos")
    assert novos.perfis == ["novo"]


def test_lote_de_novos_imediato_com_30_dias_e_limite_50(session):
    _perfil(session, "b", coletado=False)
    _perfil(session, "a", coletado=False, grupo=False, fixo=True)
    ids = agendar_lotes(session, sp(2, 9), HORARIOS)
    assert len(ids) == 1
    lote = session.get(LoteColeta, ids[0])
    assert (lote.tipo, lote.janela, lote.limite, lote.horario) == ("novos", "30 days", 50, None)
    assert lote.perfis == ["a", "b"]
    assert lote.status == "pendente"
    [job] = _jobs(session)
    assert job.payload == {"lote_id": lote.id}
    assert job.chave == f"lote:{lote.id}"
    assert job.max_tentativas == 3
    assert _lotes(session, "agendado") == []


def test_nao_cria_segundo_lote_de_novos_enquanto_um_esta_pendente(session):
    _perfil(session, "a", coletado=False)
    [primeiro] = agendar_lotes(session, sp(2, 9), HORARIOS)
    _perfil(session, "b", coletado=False)
    assert agendar_lotes(session, sp(2, 9, 5), HORARIOS) == []
    session.get(LoteColeta, primeiro).status = "executando"
    session.flush()
    assert agendar_lotes(session, sp(2, 9, 10), HORARIOS) == []
    assert len(_lotes(session, "novos")) == 1


def test_lote_de_novos_em_erro_ha_menos_de_uma_hora_bloqueia(session):
    _perfil(session, "a", coletado=False)
    [primeiro] = agendar_lotes(session, sp(2, 9), HORARIOS)
    session.get(LoteColeta, primeiro).status = "erro"
    session.flush()
    assert agendar_lotes(session, sp(2, 9, 59), HORARIOS) == []
    ids = agendar_lotes(session, sp(2, 10, 1), HORARIOS)
    assert len(ids) == 1
    assert session.get(LoteColeta, ids[0]).perfis == ["a"]


def test_lote_de_novos_em_erro_conta_a_hora_a_partir_da_falha(session):
    # criado há 2 h, falhou há 10 min: ainda bloqueia (R11: coalesce(concluido_em, criado_em))
    _perfil(session, "a", coletado=False)
    agora = sp(2, 12)
    session.add(LoteColeta(
        tipo="novos", janela="30 days", limite=50, perfis=["a"], status="erro",
        criado_em=agora - timedelta(hours=2), concluido_em=agora - timedelta(minutes=10),
    ))
    session.flush()
    assert agendar_lotes(session, agora, HORARIOS) == []
    assert len(agendar_lotes(session, agora + timedelta(minutes=51), HORARIOS)) == 1


def test_perfil_de_lote_de_novos_concluido_recente_nao_repete(session):
    # erro desconhecido deixa ultima_coleta_em nula: não pode virar um lote a cada 5 min.
    _perfil(session, "a", coletado=False)
    [primeiro] = agendar_lotes(session, sp(2, 9), HORARIOS)
    lote = session.get(LoteColeta, primeiro)
    lote.status, lote.concluido_em = "concluido", sp(2, 9, 2)
    _perfil(session, "b", coletado=False)
    [segundo] = agendar_lotes(session, sp(2, 9, 5), HORARIOS)
    assert session.get(LoteColeta, segundo).perfis == ["b"]
    session.get(LoteColeta, segundo).status = "concluido"
    session.flush()
    assert agendar_lotes(session, sp(2, 9, 10), HORARIOS) == []
    ids = agendar_lotes(session, sp(2, 10, 6), HORARIOS)
    assert session.get(LoteColeta, ids[0]).perfis == ["a", "b"]


def test_sem_perfis_acompanhados_nao_cria_lote(session):
    _perfil(session, "solto", grupo=False)
    _perfil(session, "solto_novo", grupo=False, coletado=False)
    _perfil(session, "privado", status="privado", coletado=False)
    assert agendar_lotes(session, sp(2, 9), HORARIOS) == []
    assert _lotes(session) == []
    assert _jobs(session) == []


@pytest.fixture
def fabrica(engine):
    def limpar():
        with engine.begin() as conn:
            conn.execute(text(
                "TRUNCATE lotes_coleta, jobs, grupo_perfis, grupos, usuarios, perfis "
                "RESTART IDENTITY CASCADE"
            ))

    limpar()
    yield sessionmaker(engine, expire_on_commit=False)
    limpar()


def test_duas_manutencoes_simultaneas_criam_um_so_lote_de_novos(fabrica):
    with fabrica.begin() as s:
        _perfil(s, "a", coletado=False)
    agora = sp(2, 9)
    resultado = {}

    def segunda():
        with fabrica.begin() as s2:
            resultado["ids"] = agendar_lotes(s2, agora, HORARIOS)

    with fabrica.begin() as s1:
        primeiros = agendar_lotes(s1, agora, HORARIOS)
        t = threading.Thread(target=segunda)
        t.start()
        t.join(timeout=1)
        # a segunda espera o lock da primeira transação
        assert t.is_alive()
    t.join(timeout=10)
    assert not t.is_alive()
    assert len(primeiros) == 1
    assert resultado["ids"] == []
    with fabrica() as s:
        assert s.scalar(select(func.count()).select_from(LoteColeta)) == 1
