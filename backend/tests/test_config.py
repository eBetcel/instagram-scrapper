from pathlib import Path
from agenda.config import get_settings


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
