"""Fusão de eventos duplicados que já estão no banco."""

import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, cast, delete, func, select, update
from sqlalchemy.orm import Session

from agenda.extracao.regras import FUSO
from agenda.models import Evento, EventoFonte, RevisaoEvento
from agenda.reconciliacao.aplicar import _ORDEM, _alterar, _falta
from agenda.reconciliacao.candidatos import JANELA_PASSADO, normalizar_artistas
from agenda.reconciliacao.identidade import mesmo_evento

log = logging.getLogger(__name__)


def _campos(ev: Evento) -> dict[str, Any]:
    campos = {c: getattr(ev, c) for c in _ORDEM}
    return {**campos, "hora_definida": ev.hora_definida, "artistas_norm": ev.artistas_norm}


def fundir(s: Session, manter: Evento, remover: Evento, motivo: str) -> None:
    """Leva fontes e revisões de `remover` para `manter`, preenche o que faltava em
    `manter`, une os artistas e apaga `remover`."""
    with s.begin_nested():
        ja = set(s.scalars(select(EventoFonte.post_id).where(EventoFonte.evento_id == manter.id)))
        s.execute(delete(EventoFonte).where(
            EventoFonte.evento_id == remover.id, EventoFonte.post_id.in_(ja)
        ))
        s.execute(update(EventoFonte).where(EventoFonte.evento_id == remover.id)
                  .values(evento_id=manter.id))
        s.execute(update(RevisaoEvento).where(RevisaoEvento.evento_id == remover.id)
                  .values(evento_id=manter.id))

        outro = _campos(remover)
        artistas = list(manter.artistas or [])
        vistos = set(normalizar_artistas(artistas))
        for a in remover.artistas or []:
            norm = normalizar_artistas([a])
            if norm and norm[0] not in vistos:
                artistas.append(a)
                vistos.add(norm[0])
        outro["artistas"] = artistas
        outro["artistas_norm"] = normalizar_artistas(artistas)
        for campo in _ORDEM:
            if campo == "artistas":
                if artistas != list(manter.artistas or []):
                    _alterar(s, manter, campo, outro, None, motivo)
            elif campo == "status":
                if manter.status == "ativo" and remover.status != "ativo":
                    _alterar(s, manter, campo, outro, None, motivo)
            elif _falta(manter, campo, outro):
                _alterar(s, manter, campo, outro, None, motivo)
        s.flush()
        s.delete(remover)
        s.flush()
    log.warning("evento %s fundido em %s (%s)", remover.id, manter.id, manter.titulo)


def _n_fontes(s: Session, ids: list[int]) -> dict[int, int]:
    return dict(s.execute(
        select(EventoFonte.evento_id, func.count())
        .where(EventoFonte.evento_id.in_(ids))
        .group_by(EventoFonte.evento_id)
    ).all())


def deduplicar(
    s: Session, *, agora: datetime, eventos: list[Evento] | None = None
) -> list[tuple[int, int]]:
    """Funde, dia a dia, os pares com `mesmo_evento` até não sobrar nenhum; só eventos
    futuros ou de até 7 dias atrás. Com `eventos`, só os dias deles. Devolve os pares
    (mantido, removido)."""
    dia = cast(func.timezone(FUSO.key, Evento.inicio), Date)
    stmt = select(Evento).where(
        func.coalesce(Evento.fim, Evento.inicio) >= agora - JANELA_PASSADO
    ).order_by(Evento.id)
    if eventos is not None:
        dias = {e.inicio.astimezone(FUSO).date() for e in eventos}
        if not dias:
            return []
        stmt = stmt.where(dia.in_(dias))
    por_dia: dict[date, list[Evento]] = {}
    for ev in s.scalars(stmt):
        por_dia.setdefault(ev.inicio.astimezone(FUSO).date(), []).append(ev)

    fusoes: list[tuple[int, int]] = []
    for grupo in por_dia.values():
        while par := _primeiro_par(grupo):
            fontes = _n_fontes(s, [par[0].id, par[1].id])
            manter, remover = sorted(par, key=lambda e: (-fontes.get(e.id, 0), e.id))
            fusoes.append((manter.id, remover.id))
            fundir(s, manter, remover, f"fusão de duplicata (evento {remover.id})")
            grupo.remove(remover)
    return fusoes


def _primeiro_par(eventos: list[Evento]) -> tuple[Evento, Evento] | None:
    for i, a in enumerate(eventos):
        for b in eventos[i + 1:]:
            if mesmo_evento(a, b):
                return a, b
    return None
