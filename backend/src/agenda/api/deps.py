"""Dependências por requisição: sessão de banco e usuário logado."""

from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from agenda.api.seguranca import hash_valor
from agenda.models import Sessao, Usuario

COOKIE_SESSAO = "sessao"


def deps_api(request: Request):
    return request.app.state.deps


def sessao_db(request: Request) -> Iterator[Session]:
    """Uma sessão por requisição: commit no fim, rollback em erro."""
    s = request.app.state.deps.fabrica()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def usuario_opcional(request: Request, s: Session = Depends(sessao_db)) -> Usuario | None:
    token = request.cookies.get(COOKIE_SESSAO)
    if not token:
        return None
    agora = request.app.state.deps.relogio()
    return s.scalar(
        select(Usuario)
        .join(Sessao, Sessao.usuario_id == Usuario.id)
        .where(Sessao.token_hash == hash_valor(token), Sessao.expira_em > agora)
    )


def usuario_atual(usuario: Usuario | None = Depends(usuario_opcional)) -> Usuario:
    if usuario is None:
        raise HTTPException(401, "Faça login para continuar")
    return usuario
