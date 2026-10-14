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
# Sigla ou nome de estado no campo cidade não diz a cidade: conta como vazio.
# São Paulo e Rio de Janeiro ficam de fora: no campo cidade, quase sempre são a capital.
ESTADOS = frozenset([
    "ac", "al", "ap", "am", "ba", "ce", "df", "es", "go", "ma", "mt", "ms", "mg", "pa", "pb",
    "pr", "pe", "pi", "rj", "rn", "rs", "ro", "rr", "sc", "sp", "se", "to",
    "acre", "alagoas", "amapa", "amazonas", "bahia", "ceara", "distrito federal",
    "espirito santo", "goias", "maranhao", "mato grosso", "mato grosso do sul",
    "minas gerais", "para", "paraiba", "parana", "pernambuco", "piaui",
    "rio grande do norte", "rio grande do sul", "rondonia", "roraima", "santa catarina",
    "sergipe", "tocantins",
])
_ANO = re.compile(r"^(19|20)\d\d$")


def tokens(texto: str | None) -> set[str]:
    """Tokens sem palavras vazias nem ano ("Festival DoSol 2026" ~ "Festival DoSol")."""
    return {t for t in normalizar(texto).split() if t not in PALAVRAS_VAZIAS and not _ANO.match(t)}


def cidade_norm(cidade: str | None) -> str:
    """'ARACAJU/SE' -> 'aracaju'; 'Natal - RN' -> 'natal'; 'RN' -> '' (estado)."""
    nome = normalizar(re.split(r"[/-]", cidade or "")[0])
    return "" if nome in ESTADOS else nome


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
    ca, cb = cidade_norm(a.cidade), cidade_norm(b.cidade)
    if ca and cb and ca != cb:
        return False
    if a.hora_definida and b.hora_definida and not festival and a.inicio != b.inicio:
        return False
    return True


def pares_fortes(evento: Evento, candidatos: list[Evento]) -> list[Evento]:
    """Candidatos que são, deterministicamente, o mesmo evento que `evento`."""
    return [c for c in candidatos if mesmo_evento(evento, c)]
