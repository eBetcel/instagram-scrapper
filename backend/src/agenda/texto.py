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
