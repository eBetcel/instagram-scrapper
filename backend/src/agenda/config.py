import re
from datetime import time
from decimal import Decimal
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# (entrada, saida) em USD por 1M de tokens.
PRECOS_POR_MILHAO: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4.1-mini": (Decimal("0.40"), Decimal("1.60")),
    "gpt-4.1-nano": (Decimal("0.10"), Decimal("0.40")),
}


DATABASE_URL_PADRAO = "postgresql+psycopg://agenda:agenda@localhost:5432/agenda"
HORARIOS_COLETA_PADRAO = "08:00,18:00"

_HH_MM = re.compile(r"(\d{2}):(\d{2})")


def parse_horarios(texto: str) -> list[time]:
    """`"08:00,18:00"` -> horários (em America/Sao_Paulo), ordenados e sem repetição."""
    horarios = set()
    for parte in texto.split(","):
        m = _HH_MM.fullmatch(parte.strip())
        if m is None or int(m[1]) > 23 or int(m[2]) > 59:
            raise ValueError(
                f"HORARIOS_COLETA inválido: {texto!r} (use HH:MM separados por vírgula, ex. 08:00,18:00)"
            )
        horarios.add(time(int(m[1]), int(m[2])))
    return sorted(horarios)


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
    apify_token: str = ""
    apify_actor_id: str = "nH2AHrwxeTRJoN5hX"
    apify_preco_por_post: Decimal = Decimal("0.0017")
    horarios_coleta: str = HORARIOS_COLETA_PADRAO
    s3_endpoint: str = "http://localhost:8333"
    s3_bucket: str = "flyers"
    s3_access_key: str = "agenda"
    s3_secret_key: str = "agenda-secret"

    @field_validator("horarios_coleta")
    @classmethod
    def _valida_horarios(cls, v: str) -> str:
        parse_horarios(v)
        return v


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
