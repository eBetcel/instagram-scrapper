"""Normalização de texto compartilhada pela extração e pela reconciliação."""

import re
import unicodedata


def normalizar(texto: str | None) -> str:
    """Minúsculas, sem acento, pontuação vira espaço, espaços colapsados."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c)
    )
    return " ".join(re.sub(r"[^\w]+", " ", sem_acento.lower()).split())


def slugificar(nome: str) -> str:
    """'Jazz em Natal' -> 'jazz-em-natal'; sem letras nem dígitos -> 'grupo'."""
    return "-".join(normalizar(nome).replace("_", " ").split()) or "grupo"


_USERNAME = re.compile(r"^[a-z0-9._]{1,30}$")


def normalizar_username(bruto: str) -> str | None:
    """'  @Casa.Azul ' -> 'casa.azul'; None se não for um @ válido do Instagram."""
    username = bruto.strip().removeprefix("@").lower()
    return username if _USERNAME.match(username) else None
