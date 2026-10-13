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
