import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from agenda import db


def test_session_scope_faz_rollback_em_erro(monkeypatch):
    engine = create_engine("sqlite://")
    with engine.begin() as c:
        c.execute(text("create table t (id integer)"))
    monkeypatch.setattr(db, "get_session_factory", lambda: sessionmaker(engine))

    with pytest.raises(RuntimeError):
        with db.session_scope() as s:
            s.execute(text("insert into t values (1)"))
            raise RuntimeError("falha")

    with db.session_scope() as s:
        assert s.execute(text("select count(*) from t")).scalar() == 0
        s.execute(text("insert into t values (2)"))
    with db.session_scope() as s:
        assert s.execute(text("select count(*) from t")).scalar() == 1
