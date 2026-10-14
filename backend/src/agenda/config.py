from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# (entrada, saida) em USD por 1M de tokens.
PRECOS_POR_MILHAO: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4.1-mini": (Decimal("0.40"), Decimal("1.60")),
    "gpt-4.1-nano": (Decimal("0.10"), Decimal("0.40")),
}


DATABASE_URL_PADRAO = "postgresql+psycopg://agenda:agenda@localhost:5432/agenda"


class ConfigBanco(BaseSettings):
    """Só o necessário para falar com o banco (Alembic não depende da OpenAI)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = DATABASE_URL_PADRAO


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = DATABASE_URL_PADRAO
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


class ConfigApi(BaseSettings):
    """Configuração da api (não exige as variáveis da OpenAI)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = DATABASE_URL_PADRAO
    app_url: str = "http://localhost:3000"
    smtp_host: str = "localhost"
    smtp_porta: int = 1025
    smtp_usuario: str = ""
    smtp_senha: str = ""
    smtp_tls: bool = False
    email_remetente: str = "agenda@localhost"
    cookie_seguro: bool = False
    limite_grupos_por_usuario: int = 10
    limite_perfis_por_usuario: int = 30
    s3_endpoint: str = "http://localhost:8333"
    s3_bucket: str = "flyers"
    s3_access_key: str = "agenda"
    s3_secret_key: str = "agenda-secret"


@lru_cache
def get_config_api() -> ConfigApi:
    return ConfigApi()


@lru_cache
def get_settings() -> Settings:
    return Settings()
