"""Fábrica da api FastAPI do produto web (todas as rotas sob /api)."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker

from agenda.api import auth, eventos, grupos
from agenda.config import ConfigApi
from agenda.email import EnviadorEmail
from agenda.storage import Storage


@dataclass
class DependenciasApi:
    fabrica: sessionmaker[Session]
    config: ConfigApi
    enviador: EnviadorEmail
    storage: Storage
    relogio: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))


def criar_app(deps: DependenciasApi) -> FastAPI:
    app = FastAPI(title="Agenda", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.deps = deps
    app.include_router(auth.rotas)
    app.include_router(grupos.rotas)
    app.include_router(eventos.rotas)
    return app


def app_real() -> FastAPI:
    """App com as implementações de verdade (SMTP, S3, banco do DATABASE_URL)."""
    from sqlalchemy import create_engine

    from agenda.config import get_config_api
    from agenda.email import SmtpEnviador
    from agenda.storage import S3Storage

    config = get_config_api()
    fabrica = sessionmaker(create_engine(config.database_url), expire_on_commit=False)
    return criar_app(DependenciasApi(
        fabrica=fabrica, config=config, enviador=SmtpEnviador(config),
        storage=S3Storage.from_settings(config),
    ))
