"""Tipos da coleta em lote (independentes da fonte)."""

from __future__ import annotations

from collections.abc import Callable
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
    # Itens de post (sem `error`) que a fonte devolveu, antes de descartes e deduplicação:
    # é o que a Apify cobra.
    itens_cobrados: int = 0


class Coletor(Protocol):
    def coletar(
        self,
        usernames: list[str],
        *,
        janela: str,
        limite: int,
        run_id: str | None = None,
        ao_iniciar: Callable[[str], None] | None = None,
    ) -> ResultadoLote:
        """Coleta numa execução. ``run_id``: execução já iniciada numa tentativa
        anterior, a reaproveitar. ``ao_iniciar``: chamado com o id de cada execução
        nova, logo depois de iniciá-la."""
        ...


class FakeColetor:
    """Coletor de testes: devolve só posts/erros dos usernames pedidos.

    Sem ``run_id``, "inicia" uma execução ``fake-N`` e a avisa a ``ao_iniciar``; com
    ``run_id``, reaproveita-a. ``runs_recebidos`` guarda o ``run_id`` de cada chamada.
    """

    def __init__(
        self, posts: list[PostColetado], erros: dict[str, str] | None = None
    ) -> None:
        self._posts = posts
        self._erros = erros or {}
        self.chamadas: list[tuple[list[str], str, int]] = []
        self.runs_recebidos: list[str | None] = []
        self._iniciados = 0

    def coletar(
        self,
        usernames: list[str],
        *,
        janela: str,
        limite: int,
        run_id: str | None = None,
        ao_iniciar: Callable[[str], None] | None = None,
    ) -> ResultadoLote:
        self.chamadas.append((list(usernames), janela, limite))
        self.runs_recebidos.append(run_id)
        if run_id is None:
            self._iniciados += 1
            run_id = f"fake-{self._iniciados}"
            if ao_iniciar is not None:
                ao_iniciar(run_id)
        pedidos = set(usernames)
        posts = [p for p in self._posts if p.perfil in pedidos]
        return ResultadoLote(
            posts=posts,
            erros={u: m for u, m in self._erros.items() if u in pedidos},
            run_ids=[run_id],
            itens_cobrados=len(posts),
        )
