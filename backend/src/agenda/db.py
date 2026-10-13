from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from agenda.config import get_settings


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    engine = create_engine(get_settings().database_url)
    return sessionmaker(engine, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
