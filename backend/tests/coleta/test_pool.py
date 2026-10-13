from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from agenda.coleta.base import SemContasDisponiveis
from agenda.coleta.pool import PoolContas, cifrar_sessao, decifrar_sessao
from agenda.models import ContaColeta

AGORA = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


@pytest.fixture
def fabrica(engine):
    f = sessionmaker(engine, expire_on_commit=False)
    with f() as s:
        s.execute(delete(ContaColeta))
        s.commit()
    yield f
    with f() as s:
        s.execute(delete(ContaColeta))
        s.commit()


def _conta(fabrica, usuario, **kw):
    with fabrica() as s:
        s.add(ContaColeta(usuario_ig=usuario, **kw))
        s.commit()


def test_cifrar_decifrar_roundtrip():
    chave = Fernet.generate_key().decode()
    token = cifrar_sessao({"sessionid": "abc", "csrftoken": "d"}, chave)
    assert "abc" not in token
    assert decifrar_sessao(token, chave) == {"sessionid": "abc", "csrftoken": "d"}
    with pytest.raises(InvalidToken):
        decifrar_sessao(token, Fernet.generate_key().decode())


def test_pool_sem_contas_levanta(fabrica):
    with pytest.raises(SemContasDisponiveis):
        PoolContas(fabrica, 10).obter(AGORA)


def test_pool_pula_conta_bloqueada(fabrica):
    _conta(fabrica, "bloq", status="bloqueada", bloqueada_ate=AGORA + timedelta(hours=1))
    _conta(fabrica, "ok")
    pool = PoolContas(fabrica, 10)
    assert pool.obter(AGORA).usuario_ig == "ok"
    with pytest.raises(SemContasDisponiveis):
        PoolContas(fabrica, 0).obter(AGORA)


def test_pool_bloqueio_expirado_volta_a_ativa(fabrica):
    _conta(fabrica, "b", status="bloqueada", bloqueada_ate=AGORA - timedelta(minutes=1))
    c = PoolContas(fabrica, 10).obter(AGORA)
    assert c.usuario_ig == "b"
    with fabrica() as s:
        row = s.scalars(select(ContaColeta)).one()
        assert row.status == "ativa"


def test_pool_pula_desativada(fabrica):
    _conta(fabrica, "d", status="desativada")
    with pytest.raises(SemContasDisponiveis):
        PoolContas(fabrica, 10).obter(AGORA)


def test_pool_respeita_limite_por_hora(fabrica):
    _conta(fabrica, "a")
    pool = PoolContas(fabrica, 2)
    pool.obter(AGORA)
    pool.obter(AGORA + timedelta(minutes=1))
    with pytest.raises(SemContasDisponiveis):
        pool.obter(AGORA + timedelta(minutes=2))
    # janela de 1h fixa a partir de janela_inicio: depois dela, zera
    assert pool.obter(AGORA + timedelta(hours=1, minutes=1)).usuario_ig == "a"
    with fabrica() as s:
        assert s.scalars(select(ContaColeta)).one().usos_janela == 1


def test_pool_prefere_menos_recentemente_usada_e_atualiza_uso(fabrica):
    _conta(fabrica, "velha", ultimo_uso_em=AGORA - timedelta(hours=3))
    _conta(fabrica, "nova", ultimo_uso_em=AGORA - timedelta(minutes=5))
    _conta(fabrica, "nunca")
    pool = PoolContas(fabrica, 10)
    assert pool.obter(AGORA).usuario_ig == "nunca"
    assert pool.obter(AGORA).usuario_ig == "velha"
    assert pool.obter(AGORA).usuario_ig == "nova"
    with fabrica() as s:
        r = s.scalars(select(ContaColeta).where(ContaColeta.usuario_ig == "nunca")).one()
        assert r.ultimo_uso_em == AGORA and r.usos_janela == 1


def test_marcar_bloqueada_persiste_e_exclui_da_selecao(fabrica):
    _conta(fabrica, "a", sessao_criptografada="tok")
    pool = PoolContas(fabrica, 10)
    conta = pool.obter(AGORA)
    assert conta.sessao_criptografada == "tok"  # utilizável após fechar a sessão
    pool.marcar_bloqueada(conta, AGORA + timedelta(hours=6))
    with fabrica() as s:
        r = s.scalars(select(ContaColeta)).one()
        assert r.status == "bloqueada" and r.bloqueada_ate == AGORA + timedelta(hours=6)
    with pytest.raises(SemContasDisponiveis):
        pool.obter(AGORA + timedelta(hours=1))
    assert pool.obter(AGORA + timedelta(hours=7)).usuario_ig == "a"
