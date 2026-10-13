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


def buscar_candidatos(
    s: Session,
    e: EventoExtraido,
    *,
    agora: datetime,
    limite: int = 5,
    limiar_titulo: float = 0.4,
) -> list[Evento]:
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

    if not criterios:
        return []

    janela = func.coalesce(Evento.fim, Evento.inicio) >= agora - JANELA_PASSADO
    stmt = (
        select(Evento)
        .where(janela, or_(*criterios))
        .order_by(escore.desc(), Evento.inicio.asc())
        .limit(limite)
    )
    return list(s.scalars(stmt))
