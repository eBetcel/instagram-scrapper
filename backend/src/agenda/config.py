from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# (entrada, saida) em USD por 1M de tokens.
PRECOS_POR_MILHAO: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4.1-mini": (Decimal("0.40"), Decimal("1.60")),
    "gpt-4.1-nano": (Decimal("0.10"), Decimal("0.40")),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://agenda:agenda@localhost:5432/agenda"
    openai_api_key: str = ""
    # Sem default no código: definidos por variável de ambiente (ver .env.example).
    openai_modelo_extracao: str
    openai_modelo_reconciliacao: str
    s3_endpoint: str = "http://localhost:8333"
    s3_bucket: str = "flyers"
    s3_access_key: str = "agenda"
    s3_secret_key: str = "agenda-secret"
    chave_sessao: str = ""  # chave Fernet das sessões do scraper
    intervalo_coleta_horas: int = 6
    limite_requisicoes_conta_hora: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
