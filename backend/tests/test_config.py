from pathlib import Path

import pytest
from pydantic import ValidationError

from agenda.config import ConfigApi, ConfigBanco, Settings, get_settings

FALSOS = {
    "APIFY_TOKEN": "apify_api_FALSO_nao_e_real_123",
    "OPENAI_API_KEY": "sk-FALSO-nao-e-real-456",
    "S3_SECRET_KEY": "s3-FALSO-segredo-789",
    "SMTP_SENHA": "smtp-FALSA-senha-000",
}


@pytest.fixture
def segredos_falsos(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # sem .env
    for k, v in FALSOS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("OPENAI_MODELO_EXTRACAO", "x")
    monkeypatch.setenv("OPENAI_MODELO_RECONCILIACAO", "y")


def _sem_segredos(texto: str) -> None:
    for v in FALSOS.values():
        assert v not in texto


@pytest.mark.parametrize("quebra", ["falta_modelo", "horarios_invalidos"])
def test_erro_de_validacao_das_settings_nao_mostra_segredos(segredos_falsos, monkeypatch, quebra):
    # Campo obrigatório ausente: o pydantic põe a entrada inteira (com os segredos) no erro.
    if quebra == "falta_modelo":
        monkeypatch.delenv("OPENAI_MODELO_EXTRACAO")
    else:
        monkeypatch.setenv("HORARIOS_COLETA", "8h")
    with pytest.raises(ValidationError) as e:
        Settings()
    _sem_segredos(str(e.value))
    _sem_segredos(repr(e.value))


def test_erro_de_validacao_da_config_api_nao_mostra_segredos(segredos_falsos, monkeypatch):
    monkeypatch.setenv("SMTP_PORTA", "abc")
    with pytest.raises(ValidationError) as e:
        ConfigApi()
    _sem_segredos(str(e.value))
    _sem_segredos(repr(e.value))


def test_configs_escondem_a_entrada_nos_erros():
    for cls in (Settings, ConfigApi, ConfigBanco):
        assert cls.model_config.get("hide_input_in_errors") is True


def test_repr_das_settings_nao_mostra_segredos(segredos_falsos):
    s = Settings()
    _sem_segredos(repr(s))
    _sem_segredos(str(s))
    _sem_segredos(repr(ConfigApi()))
    assert s.apify_token.get_secret_value() == FALSOS["APIFY_TOKEN"]
    assert s.openai_api_key.get_secret_value() == FALSOS["OPENAI_API_KEY"]
    assert s.s3_secret_key.get_secret_value() == FALSOS["S3_SECRET_KEY"]
    assert ConfigApi().smtp_senha.get_secret_value() == FALSOS["SMTP_SENHA"]


def test_settings_le_variaveis_de_ambiente(monkeypatch):
    monkeypatch.setenv("OPENAI_MODELO_EXTRACAO", "x")
    monkeypatch.setenv("OPENAI_MODELO_RECONCILIACAO", "y")
    get_settings.cache_clear()
    try:
        assert get_settings().openai_modelo_extracao == "x"
        assert get_settings().openai_modelo_reconciliacao == "y"
    finally:
        get_settings.cache_clear()


def test_alembic_so_precisa_de_database_url(engine, monkeypatch, tmp_path):
    from alembic import command
    from alembic.config import Config
    BACKEND = Path(__file__).resolve().parents[1]

    for var in ("OPENAI_MODELO_EXTRACAO", "OPENAI_MODELO_RECONCILIACAO", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)  # sem .env
    monkeypatch.setenv("DATABASE_URL", engine.url.render_as_string(hide_password=False))
    get_settings.cache_clear()
    try:
        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND / "migrations"))
        command.upgrade(cfg, "head")  # já está em head: só conecta e confere
    finally:
        get_settings.cache_clear()
