from datetime import datetime

import pytest

from agenda.extracao.regras import FUSO
from agenda.models import Evento
from agenda.reconciliacao.identidade import cidade_norm, mesmo_evento, nomes_parecidos, tokens


def _ev(titulo="Festival Dosol 2026", inicio=datetime(2026, 12, 5, tzinfo=FUSO), **kw) -> Evento:
    kw.setdefault("hora_definida", False)
    return Evento(titulo=titulo, inicio=inicio, categoria="show", **kw)


@pytest.mark.parametrize(
    ("a", "b", "esperado"),
    [
        ("Festival Dosol 2026", "Festival Dosol 2026 na Sede Cultural Dosol", True),
        ("Jazz", "Jazz no Bar de Nazaré", True),
        ("Jáder (PE) DosolTV Sessions", "Jader DosolTV Sessions", True),
        ("Zeca Pagodino", "Zeca Pagodinho", True),
        ("Festival MADA 2026", "Festival DoSol 2026", False),
        ("Festival X 2026", "Festival Y 2026", False),
        ("Baile da Amada com Belisa", "Baile da Amada com Jader", False),
        ("de da do", "Show", False),
        (None, "Show", False),
    ],
)
def test_nomes_parecidos(a, b, esperado):
    assert nomes_parecidos(a, b) is esperado
    assert nomes_parecidos(b, a) is esperado


def test_tokens_sem_palavras_vazias_e_acentos():
    assert tokens("Show da Nanda Tsunami no MADA") == {"show", "nanda", "tsunami", "mada"}


def test_cidade_norm():
    assert cidade_norm("ARACAJU/SE") == "aracaju"
    assert cidade_norm("Natal/RN") == "natal"
    assert cidade_norm("Natal - RN") == "natal"
    assert cidade_norm(None) == ""


def test_mesmo_dia_e_titulo_parecido_e_o_mesmo():
    assert mesmo_evento(_ev(), _ev("Festival Dosol 2026 na Sede Cultural Dosol", local_nome="Sede"))


def test_outro_dia_nao_e_o_mesmo():
    assert not mesmo_evento(_ev(), _ev(inicio=datetime(2026, 12, 4, tzinfo=FUSO)))


def test_dia_e_no_fuso_de_sao_paulo():
    # 05/12 23h em SP é 06/12 02h UTC: ainda é o mesmo dia de um evento às 00h de 05/12.
    noite = datetime(2026, 12, 5, 23, 0, tzinfo=FUSO)
    assert mesmo_evento(_ev(), _ev(inicio=noite, hora_definida=True))


def test_cidades_diferentes_nao_sao_o_mesmo():
    assert not mesmo_evento(_ev("Jambu", cidade="Aracaju"), _ev("Jambu", cidade="Salvador"))


def test_cidade_so_de_um_lado_e_o_mesmo():
    assert mesmo_evento(_ev("Jambu", cidade="ARACAJU/SE"), _ev("Jambu"))
    assert mesmo_evento(_ev("Jambu", cidade="ARACAJU/SE"), _ev("Jambu", cidade="Aracaju"))


def test_horarios_definidos_diferentes_sem_festival_nao_sao_o_mesmo():
    a = _ev("Peça X", inicio=datetime(2026, 12, 5, 16, tzinfo=FUSO), hora_definida=True)
    b = _ev("Peça X", inicio=datetime(2026, 12, 5, 21, tzinfo=FUSO), hora_definida=True)
    assert not mesmo_evento(a, b)


def test_horarios_diferentes_entre_eventos_de_festival_sao_o_mesmo():
    a = _ev("Festival MADA 2026", inicio=datetime(2026, 10, 16, 16, tzinfo=FUSO),
            hora_definida=True, festival="Festival MADA 2026")
    b = _ev("Festival MADA 2026", inicio=datetime(2026, 10, 16, 21, tzinfo=FUSO),
            hora_definida=True, festival="Festival MADA 2026")
    assert mesmo_evento(a, b)


def test_titulos_diferentes_mas_mesmo_festival_sao_o_mesmo():
    a = _ev("MADA — Música Alimento da Alma", inicio=datetime(2026, 10, 16, tzinfo=FUSO),
            festival="Festival MADA 2026")
    b = _ev("Festival MADA 2026 - Dia 1", inicio=datetime(2026, 10, 16, tzinfo=FUSO),
            festival="MADA 2026")
    assert mesmo_evento(a, b)
