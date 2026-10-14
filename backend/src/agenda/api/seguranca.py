"""Tokens, sessões e convites: só o SHA-256 do valor vai para o banco."""

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from agenda.models import Convite


def hash_valor(valor: str) -> str:
    return hashlib.sha256(valor.encode()).hexdigest()


def novo_token() -> str:
    return secrets.token_urlsafe(32)


# --- convites --------------------------------------------------------------------

ALFABETO_CONVITE = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # sem I, L, O, 0 e 1


def gerar_codigo_convite() -> str:
    c = "".join(secrets.choice(ALFABETO_CONVITE) for _ in range(8))
    return f"{c[:4]}-{c[4:]}"


def normalizar_codigo(bruto: str) -> str:
    return "".join(bruto.split()).replace("-", "").upper()


def criar_convite(s: Session, *, usos: int, dias: int | None, agora: datetime) -> str:
    """Grava o convite (só o hash) e devolve o código em claro, exibido uma única vez."""
    codigo = gerar_codigo_convite()
    s.add(Convite(
        codigo_hash=hash_valor(normalizar_codigo(codigo)), usos_restantes=usos,
        expira_em=agora + timedelta(days=dias) if dias else None,
    ))
    s.flush()
    return codigo


def consumir_convite(s: Session, codigo: str, agora: datetime) -> bool:
    """Gasta um uso, atomicamente: dois cadastros simultâneos não dividem o último."""
    gasto = s.execute(
        update(Convite)
        .where(
            Convite.codigo_hash == hash_valor(normalizar_codigo(codigo)),
            Convite.usos_restantes > 0,
            (Convite.expira_em.is_(None)) | (Convite.expira_em > agora),
        )
        .values(usos_restantes=Convite.usos_restantes - 1)
        .returning(Convite.id)
    ).first()
    return gasto is not None
