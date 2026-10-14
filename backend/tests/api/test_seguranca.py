import re
from datetime import UTC, datetime, timedelta

from agenda.api.seguranca import (
    consumir_convite,
    criar_convite,
    gerar_codigo_convite,
    normalizar_codigo,
)

AGORA = datetime(2026, 10, 14, 12, tzinfo=UTC)


def test_codigo_tem_formato_legivel():
    for _ in range(50):
        assert re.fullmatch(r"[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}", gerar_codigo_convite())


def test_normalizar_codigo_ignora_hifen_espaco_e_caixa():
    assert normalizar_codigo(" abcd-efgh ") == "ABCDEFGH"
    assert normalizar_codigo("AB CD EF GH") == "ABCDEFGH"


def test_convite_com_dois_usos_funciona_duas_vezes(session):
    codigo = criar_convite(session, usos=2, dias=None, agora=AGORA)
    assert consumir_convite(session, codigo, AGORA)
    assert consumir_convite(session, codigo.lower().replace("-", ""), AGORA)
    assert not consumir_convite(session, codigo, AGORA)


def test_convite_vencido_ou_inexistente_falha(session):
    codigo = criar_convite(session, usos=5, dias=7, agora=AGORA)
    assert not consumir_convite(session, codigo, AGORA + timedelta(days=8))
    assert not consumir_convite(session, "ZZZZ-ZZZZ", AGORA)
