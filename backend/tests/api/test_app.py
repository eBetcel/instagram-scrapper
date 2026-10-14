from datetime import UTC, datetime, timedelta

from apoio import logar
from sqlalchemy import update

from agenda.models import Sessao


def test_eu_sem_sessao_da_401(api):
    r = api.cliente.get("/api/eu")
    assert r.status_code == 401
    assert r.json() == {"detail": "Faça login para continuar"}


def test_eu_com_sessao_valida(api):
    u = logar(api)
    r = api.cliente.get("/api/eu")
    assert r.status_code == 200
    assert r.json() == {"id": u.id, "email": "fulana@x.com", "nome": "Fulana"}


def test_sessao_vencida_da_401(api):
    logar(api)
    with api.fabrica() as s:
        s.execute(update(Sessao).values(expira_em=datetime.now(UTC) - timedelta(minutes=1)))
        s.commit()
    assert api.cliente.get("/api/eu").status_code == 401


def test_cookie_desconhecido_da_401(api):
    api.cliente.cookies.set("sessao", "nao-existe")
    assert api.cliente.get("/api/eu").status_code == 401


def test_rota_inexistente_da_404_json(api):
    r = api.cliente.get("/api/nao-existe")
    assert r.status_code == 404
    assert "detail" in r.json()


def test_app_real_sobe_sem_variaveis_da_openai(monkeypatch, tmp_path):
    from fastapi import FastAPI

    from agenda.api.app import app_real
    from agenda.config import get_config_api

    monkeypatch.chdir(tmp_path)  # sem .env
    for var in ("OPENAI_API_KEY", "OPENAI_MODELO_EXTRACAO", "OPENAI_MODELO_RECONCILIACAO"):
        monkeypatch.delenv(var, raising=False)
    get_config_api.cache_clear()
    try:
        assert isinstance(app_real(), FastAPI)
    finally:
        get_config_api.cache_clear()


def test_cli_api_ajuda():
    from typer.testing import CliRunner

    from agenda.cli import app

    r = CliRunner().invoke(app, ["api", "--help"])
    assert r.exit_code == 0 and "--porta" in r.output
