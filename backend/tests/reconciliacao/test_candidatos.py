from datetime import date, datetime, time, timedelta, timezone

from fabricas import AGORA
from fabricas import evento as _evento
from fabricas import extraido as _extraido

from agenda.reconciliacao.candidatos import buscar_candidatos, normalizar_artistas


def test_normalizar_artistas():
    assert normalizar_artistas([" Jão ", "JAO", "Maria  Bethânia", "", "  "]) == [
        "jao",
        "maria bethania",
    ]
    assert normalizar_artistas([]) == []


def test_encontra_por_titulo_similar_com_data_diferente(session):
    ev = _evento(session, "Festival Jazz na Praça", AGORA + timedelta(days=10))
    _evento(session, "Oficina de Cerâmica Infantil")
    e = _extraido(titulo="Festival Jazz na Praça", data_inicio=date(2026, 11, 20))
    assert buscar_candidatos(session, e, agora=AGORA) == [ev]


def test_encontra_por_artista_em_comum(session):
    ev = _evento(session, "Noite de Gala", artistas=["Maria Bethânia"])
    _evento(session, "Outro Troço", artistas=["Fulano"])
    e = _extraido(titulo="Turnê Especial", artistas=["maria bethania"])
    assert buscar_candidatos(session, e, agora=AGORA) == [ev]


def test_encontra_por_local_e_dia(session):
    inicio = datetime(2026, 11, 1, 22, 0, tzinfo=timezone.utc)  # 19h em SP
    ev = _evento(session, "Qualquer Coisa", inicio, local_nome="Casa de Cultura")
    _evento(session, "Zzz", inicio + timedelta(days=1), local_nome="Casa de Cultura")
    e = _extraido(
        titulo="Xpto Wxyz", data_inicio=date(2026, 11, 1), hora_inicio=time(20, 0),
        local_nome="Casa de Cultura",
    )
    assert buscar_candidatos(session, e, agora=AGORA) == [ev]


def test_dia_usa_fuso_de_sao_paulo(session):
    # 02:00 UTC de 2/11 ainda e 1/11 em Sao Paulo
    inicio = datetime(2026, 11, 2, 2, 0, tzinfo=timezone.utc)
    ev = _evento(session, "Qualquer Coisa", inicio, local_nome="Casa de Cultura")
    e = _extraido(titulo="Xpto Wxyz", data_inicio=date(2026, 11, 1), local_nome="Casa de Cultura")
    assert buscar_candidatos(session, e, agora=AGORA) == [ev]


def test_ignora_evento_com_mais_de_7_dias_no_passado(session):
    _evento(session, "Festival Jazz na Praça", AGORA - timedelta(days=8))
    e = _extraido(titulo="Festival Jazz na Praça", data_inicio=date(2026, 10, 5))
    assert buscar_candidatos(session, e, agora=AGORA) == []


def test_exposicao_longa_em_andamento_ainda_e_candidata(session):
    ev = _evento(
        session, "Exposição Mundo Novo", AGORA - timedelta(days=60), categoria="exposicao",
        fim=AGORA + timedelta(days=30),
    )
    e = _extraido(titulo="Exposição Mundo Novo", categoria="exposicao")
    assert buscar_candidatos(session, e, agora=AGORA) == [ev]


def test_respeita_limite_de_10(session):
    for i in range(12):
        _evento(session, f"Festival Jazz na Praça {i}")
    e = _extraido(titulo="Festival Jazz na Praça")
    assert len(buscar_candidatos(session, e, agora=AGORA)) == 10


def test_mesmo_titulo_em_outro_local_ainda_e_candidato_mas_nao_o_unico(session):
    a = _evento(session, "Festival Jazz na Praça", local_nome="Praça A")
    b = _evento(session, "Festival Jazz na Praça", local_nome="Praça B")
    e = _extraido(titulo="Festival Jazz na Praça", local_nome="Praça A")
    assert {x.id for x in buscar_candidatos(session, e, agora=AGORA)} == {a.id, b.id}


def test_ordena_por_escore(session):
    fraco = _evento(session, "Festival Jazz Praça Central")
    forte = _evento(session, "Festival Jazz na Praça", artistas=["Fulano"])
    e = _extraido(titulo="Festival Jazz na Praça", artistas=["Fulano"])
    assert buscar_candidatos(session, e, agora=AGORA) == [forte, fraco]


def test_sem_candidatos_retorna_lista_vazia(session):
    _evento(session, "Oficina de Cerâmica")
    e = _extraido(titulo="Festival Jazz na Praça")
    assert buscar_candidatos(session, e, agora=AGORA) == []


def test_sem_criterios_retorna_vazio(session):
    _evento(session, "Oficina de Cerâmica")
    assert buscar_candidatos(session, _extraido(), agora=AGORA) == []


def test_inclui_o_do_mesmo_dia_mesmo_com_muitos_titulos_parecidos_em_outras_datas(session):
    from agenda.extracao.regras import FUSO
    for i in range(12):
        _evento(session, "Festival Dosol 2026", datetime(2026, 11, 1 + i, tzinfo=FUSO), hora_definida=False)
    alvo = _evento(session, "Festival Dosol 2026 na Sede Cultural Dosol",
                   datetime(2026, 12, 5, tzinfo=FUSO), hora_definida=False)
    e = _extraido(titulo="Festival Dosol 2026", data_inicio=date(2026, 12, 5), local_nome="Sede Dosol")
    cands = buscar_candidatos(session, e, agora=AGORA)
    assert alvo in cands
    assert len(cands) <= 10


def test_inclui_o_do_mesmo_dia_pelo_festival(session):
    from agenda.extracao.regras import FUSO
    alvo = _evento(session, "MADA — Música Alimento da Alma", datetime(2026, 10, 16, tzinfo=FUSO),
                   hora_definida=False, festival="Festival MADA 2026")
    e = _extraido(titulo="Festival MADA 2026", data_inicio=date(2026, 10, 16), festival="Festival MADA 2026")
    assert alvo in buscar_candidatos(session, e, agora=AGORA)
