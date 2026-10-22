"""Fixtures da api: TestClient sobre o Postgres do testcontainer, com commit real e
TRUNCATE antes e depois (como em tests/test_cli.py)."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from agenda.api.app import DependenciasApi, criar_app
from agenda.config import ConfigApi
from agenda.email import FakeEnviador
from agenda.storage import MemoriaStorage

TABELAS = (
    "grupo_seguidores, grupo_perfis, grupos, sessoes, tokens_login, convites, usuarios, "
    "revisoes_evento, evento_fontes, eventos, posts, perfis, jobs"
)


@pytest.fixture
def api(engine):
    def limpar():
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {TABELAS} RESTART IDENTITY CASCADE"))

    limpar()
    fabrica = sessionmaker(engine, expire_on_commit=False)
    enviador, storage = FakeEnviador(), MemoriaStorage()
    deps = DependenciasApi(
        fabrica=fabrica, config=ConfigApi(), enviador=enviador, storage=storage,
    )
    with TestClient(criar_app(deps)) as cliente:
        yield SimpleNamespace(cliente=cliente, enviador=enviador, storage=storage, fabrica=fabrica)
    limpar()
