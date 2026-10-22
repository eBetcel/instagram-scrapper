"""Serviço de coleta.

Nenhuma função faz commit: a transação pertence a quem chama.
"""

import urllib.request


def baixar_url(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()
