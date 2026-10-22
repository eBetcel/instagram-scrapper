"""Migração 0004 num banco descartável (não mexe no banco compartilhado da sessão)."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

BACKEND = Path(__file__).resolve().parents[1]

BANCO = "mig_0004"


@pytest.fixture
def mig(engine):
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {BANCO}"))
        c.execute(text(f"CREATE DATABASE {BANCO}"))
    eng = create_engine(engine.url.set(database=BANCO))
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))

    def migrar(acao, alvo):
        with eng.begin() as conn:
            cfg.attributes["connection"] = conn
            acao(cfg, alvo)

    try:
        yield eng, migrar
    finally:
        eng.dispose()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {BANCO} WITH (FORCE)"))


def test_0004_remove_contas_proxima_e_jobs_de_coleta(mig):
    eng, migrar = mig
    migrar(command.upgrade, "0003")
    with eng.begin() as c:
        c.execute(text("INSERT INTO contas_coleta (usuario_ig) VALUES ('conta')"))
        c.execute(text(
            "INSERT INTO perfis (username, status, ultima_coleta_em) VALUES "
            "('nunca', 'inexistente', NULL), ('coletado', 'inexistente', now()), "
            "('normal', 'ativo', NULL)"
        ))
        c.execute(text(
            "INSERT INTO jobs (tipo, chave, payload) VALUES "
            "('coletar_perfil', 'coletar:1', '{\"perfil_id\": 1}'), "
            "('extrair_post', 'extrair:1', '{\"post_id\": 1}')"
        ))

    migrar(command.upgrade, "0004")

    insp = inspect(eng)
    assert "contas_coleta" not in insp.get_table_names()
    assert "proxima_coleta_em" not in {c["name"] for c in insp.get_columns("perfis")}
    with eng.connect() as c:
        assert c.execute(text("SELECT tipo FROM jobs")).scalars().all() == ["extrair_post"]
        status = dict(c.execute(text("SELECT username, status FROM perfis")).all())
    assert status == {"nunca": "ativo", "coletado": "inexistente", "normal": "ativo"}


def test_0004_downgrade(mig):
    eng, migrar = mig
    migrar(command.upgrade, "0004")
    migrar(command.downgrade, "0003")

    insp = inspect(eng)
    assert "contas_coleta" in insp.get_table_names()
    assert "proxima_coleta_em" in {c["name"] for c in insp.get_columns("perfis")}
    with eng.begin() as c:
        c.execute(text("INSERT INTO contas_coleta (usuario_ig) VALUES ('conta')"))
        assert c.execute(text("SELECT status, usos_janela FROM contas_coleta")).one() == ("ativa", 0)
