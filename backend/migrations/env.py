from alembic import context
from sqlalchemy import create_engine

from agenda.config import ConfigBanco
from agenda.models import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_online() -> None:
    # Conexão injetada (testes) tem prioridade; depois sqlalchemy.url; por fim DATABASE_URL
    # (ConfigBanco: não exige as variáveis da OpenAI).
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    url = config.get_main_option("sqlalchemy.url") or ConfigBanco().database_url
    engine = create_engine(url)
    with engine.connect() as conn:
        _run(conn)
    engine.dispose()


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
