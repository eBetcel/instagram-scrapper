"""Identidade determinística de eventos: decide, sem o modelo, se dois eventos são o mesmo."""

import re
from difflib import SequenceMatcher

from agenda.extracao.regras import FUSO
from agenda.models import Evento
from agenda.texto import normalizar

PALAVRAS_VAZIAS = frozenset(
    "a o as os de da do das dos e em no na nos nas com para pra por".split()
)
LIMIAR_DIGITACAO = 0.8


def tokens(texto: str | None) -> set[str]:
    return set(normalizar(texto).split()) - PALAVRAS_VAZIAS


def cidade_norm(cidade: str | None) -> str:
    """'ARACAJU/SE' -> 'aracaju'; 'Natal - RN' -> 'natal'."""
    return normalizar(re.split(r"[/-]", cidade or "")[0])


def nomes_parecidos(a: str | None, b: str | None) -> bool:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    if normalizar(a) == normalizar(b) or ta <= tb or tb <= ta:
        return True
    # Só os tokens que diferem: os comuns ("festival", "2026") inflariam a razão.
    so_a, so_b = " ".join(sorted(ta - tb)), " ".join(sorted(tb - ta))
    return SequenceMatcher(None, so_a, so_b).ratio() >= LIMIAR_DIGITACAO


def mesmo_evento(a: Evento, b: Evento) -> bool:
    """Mesmo dia (em São Paulo) e nome ou festival parecido, sem cidades diferentes
    nem, fora de festival, horários definidos diferentes."""
    if a.inicio.astimezone(FUSO).date() != b.inicio.astimezone(FUSO).date():
        return False
    festival = bool(a.festival and b.festival)
    if not (
        nomes_parecidos(a.titulo, b.titulo)
        or (festival and nomes_parecidos(a.festival, b.festival))
    ):
        return False
    if a.cidade and b.cidade and cidade_norm(a.cidade) != cidade_norm(b.cidade):
        return False
    if a.hora_definida and b.hora_definida and not festival and a.inicio != b.inicio:
        return False
    return True


def pares_fortes(evento: Evento, candidatos: list[Evento]) -> list[Evento]:
    """Candidatos que são, deterministicamente, o mesmo evento que `evento`."""
    return [c for c in candidatos if mesmo_evento(evento, c)]
