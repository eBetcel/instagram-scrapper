from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


# Instagram mostra até 3 posts fixados no topo do perfil; como o marcador de
# fixado pode não vir no node, os 3 primeiros posts são tratados como possivelmente fixados.
MAX_FIXADOS = 3


class PerfilPrivado(Exception):
    pass


class PerfilInexistente(Exception):
    pass


class ContaBloqueada(Exception):
    pass


class SemContasDisponiveis(Exception):
    pass


@dataclass
class PostColetado:
    shortcode: str
    legenda: str
    publicado_em: datetime  # tz-aware, UTC
    urls_imagens: list[str] = field(default_factory=list)  # vazia para vídeo sem capa
    fixado: bool = False


class Coletor(Protocol):
    def posts_desde(self, username: str, desde: datetime | None) -> Iterable[PostColetado]:
        """Posts do perfil, mais novos primeiro."""
        ...


class FakeColetor:
    def __init__(
        self,
        posts_por_perfil: dict[str, list[PostColetado]],
        erros: dict[str, Exception] | None = None,
    ):
        self.posts_por_perfil = posts_por_perfil
        self.erros = erros or {}

    def posts_desde(self, username: str, desde: datetime | None) -> Iterator[PostColetado]:
        if username in self.erros:
            raise self.erros[username]
        yield from self.posts_por_perfil.get(username, [])
