import re
import unicodedata
from datetime import datetime, timedelta

from sqlalchemy import Date, Text, Float, and_, case, cast, func, literal, or_, select
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.orm import Session

from agenda.extracao.regras import FUSO, para_inicio
from agenda.extracao.schema import EventoExtraido
from agenda.models import Evento

JANELA_PASSADO = timedelta(days=7)
LIMIAR_LOCAL = 0.5
LIMIAR_MESMO_DIA = 0.3


def normalizar_artistas(nomes: list[str]) -> list[str]:
    """Minuscula, sem acento, espacos colapsados, sem vazios nem duplicatas."""
    vistos: dict[str, None] = {}
    for nome in nomes:
        sem_acento = "".join(
            c for c in unicodedata.normalize("NFKD", nome) if not unicodedata.combining(c)
        )
        limpo = re.sub(r"\s+", " ", sem_acento).strip().lower()
        if limpo:
            vistos.setdefault(limpo, None)
    return list(vistos)


def unir_artistas(atuais: list[str], novos: list[str]) -> list[str]:
    """`atuais` mais os `novos` que ainda não estão lá (comparação normalizada)."""
    uniao = list(atuais)
    vistos = set(normalizar_artistas(uniao))
    for a in novos:
        norm = normalizar_artistas([a])
        if norm and norm[0] not in vistos:
            uniao.append(a)
            vistos.add(norm[0])
    return uniao


def buscar_candidatos(
    s: Session,
    e: EventoExtraido,
    *,
    agora: datetime,
    limite: int = 10,
    limiar_titulo: float = 0.4,
) -> list[Evento]:
    janela = func.coalesce(Evento.fim, Evento.inicio) >= agora - JANELA_PASSADO
    do_dia = _do_mesmo_dia(s, e, janela, limite)
    criterios = []
    escore = literal(0.0, Float)

    if e.titulo and e.titulo.strip():
        sim = func.similarity(Evento.titulo, e.titulo)
        criterios.append(sim >= limiar_titulo)
        escore = escore + sim

    artistas = normalizar_artistas(e.artistas)
    if artistas:
        sobrepoe = cast(Evento.artistas_norm, PG_ARRAY(Text)).overlap(artistas)
        criterios.append(sobrepoe)
        escore = escore + case((sobrepoe, 1.0), else_=0.0)

    if e.local_nome and e.local_nome.strip() and e.data_inicio is not None:
        mesmo_dia = (
            cast(func.timezone(FUSO.key, Evento.inicio), Date) == para_inicio(e)[0].date()
        )
        local = and_(
            Evento.local_nome.is_not(None),
            func.similarity(Evento.local_nome, e.local_nome) >= LIMIAR_LOCAL,
            mesmo_dia,
        )
        criterios.append(local)
        escore = escore + case((local, 1.0), else_=0.0)

    if not criterios or len(do_dia) >= limite:
        return do_dia

    stmt = (
        select(Evento)
        .where(janela, or_(*criterios), Evento.id.not_in([c.id for c in do_dia]))
        .order_by(escore.desc(), Evento.inicio.asc())
        .limit(limite - len(do_dia))
    )
    return do_dia + list(s.scalars(stmt))


def _do_mesmo_dia(s: Session, e: EventoExtraido, janela, limite: int) -> list[Evento]:
    """Eventos do mesmo dia com título ou festival parecido: entram sempre, para que o
    par certo não seja empurrado para fora por títulos parecidos em outras datas."""
    if e.data_inicio is None:
        return []
    nomes = [n for n in (e.titulo, e.festival) if n and n.strip()]
    if not nomes:
        return []
    sim = func.greatest(
        *[func.similarity(func.coalesce(col, ""), n) for col in (Evento.titulo, Evento.festival) for n in nomes]
    )
    mesmo_dia = cast(func.timezone(FUSO.key, Evento.inicio), Date) == e.data_inicio
    stmt = (
        select(Evento)
        .where(janela, mesmo_dia, sim >= LIMIAR_MESMO_DIA)
        .order_by(sim.desc(), Evento.id)
        .limit(limite)
    )
    return list(s.scalars(stmt))
