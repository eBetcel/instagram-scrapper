"""Tipos da coleta em lote (independentes da fonte)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class PostColetado:
    shortcode: str
    legenda: str
    publicado_em: datetime
    urls_imagens: list[str]
    perfil: str  # username pedido, em minúsculas


@dataclass
class ResultadoLote:
    posts: list[PostColetado] = field(default_factory=list)
    erros: dict[str, str] = field(default_factory=dict)
    run_ids: list[str] = field(default_factory=list)


class Coletor(Protocol):
    def coletar(
        self, usernames: list[str], *, janela: str, limite: int
    ) -> ResultadoLote: ...


class FakeColetor:
    """Coletor de testes: devolve só posts/erros dos usernames pedidos."""

    def __init__(
        self, posts: list[PostColetado], erros: dict[str, str] | None = None
    ) -> None:
        self._posts = posts
        self._erros = erros or {}
        self.chamadas: list[tuple[list[str], str, int]] = []

    def coletar(
        self, usernames: list[str], *, janela: str, limite: int
    ) -> ResultadoLote:
        self.chamadas.append((list(usernames), janela, limite))
        pedidos = set(usernames)
        return ResultadoLote(
            posts=[p for p in self._posts if p.perfil in pedidos],
            erros={u: m for u, m in self._erros.items() if u in pedidos},
            run_ids=[],
        )
