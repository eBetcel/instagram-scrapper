import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture(scope="session")
def engine():
    # Import e container só quando algum teste pede Postgres.
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16", driver="psycopg") as pg:
        eng = create_engine(pg.get_connection_url())
        # Task 2: rodar `alembic upgrade head` aqui.
        yield eng
        eng.dispose()


@pytest.fixture
def session(engine):
    conn = engine.connect()
    trans = conn.begin()
    s = Session(conn, join_transaction_mode="create_savepoint")
    try:
        yield s
    finally:
        s.close()
        trans.rollback()
        conn.close()
