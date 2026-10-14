"""Tokens, sessões e convites: só o SHA-256 do valor vai para o banco."""

import hashlib
import secrets


def hash_valor(valor: str) -> str:
    return hashlib.sha256(valor.encode()).hexdigest()


def novo_token() -> str:
    return secrets.token_urlsafe(32)
