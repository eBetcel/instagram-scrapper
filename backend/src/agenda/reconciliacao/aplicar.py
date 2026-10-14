"""Efeitos transacionais da reconciliacao (Etapa C)."""

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from agenda.extracao.regras import FUSO, normalizar_preco, para_fim, para_inicio
from agenda.extracao.schema import EventoExtraido
from agenda.models import Evento, EventoFonte, Post, RevisaoEvento
from agenda.reconciliacao.candidatos import normalizar_artistas
from agenda.reconciliacao.decisao import (
    CAMPOS_PERMITIDOS,
    Campo,
    Decisao,
    DecisaoInvalida,
    evento_id_valido,
    eventos_do_post,
)

log = logging.getLogger(__name__)

__all__ = ["DecisaoInvalida", "aplicar", "campos_do_evento"]

# Ordem estavel para aplicar/registrar revisoes.
_ORDEM: tuple[Campo, ...] = (
    "titulo", "descricao", "inicio", "fim", "local_nome", "endereco", "cidade", "categoria",
    "preco_texto", "gratuito", "preco_min", "preco_max", "link_ingresso", "artistas", "festival",
    "status",
)
# Colunas derivadas, gravadas junto com o campo principal (sem revisao propria).
_DERIVADAS = {"inicio": "hora_definida", "artistas": "artistas_norm"}


def _decimal(v: float | None) -> Decimal | None:
    return Decimal(str(v)) if v is not None else None


def campos_do_evento(e: EventoExtraido) -> dict[str, Any]:
    """Mapeamento unico EventoExtraido -> colunas de Evento (R21)."""
    e = normalizar_preco(e)
    inicio, hora_definida = para_inicio(e)
    return {
        "titulo": e.titulo.strip() if e.titulo else e.titulo,
        "descricao": e.descricao,
        "inicio": inicio,
        "hora_definida": hora_definida,
        "fim": para_fim(e),
        "local_nome": e.local_nome,
        "endereco": e.endereco,
        "cidade": e.cidade,
        "categoria": e.categoria,
        "preco_texto": e.preco_texto,
        "gratuito": e.gratuito,
        "preco_min": _decimal(e.preco_min),
        "preco_max": _decimal(e.preco_max),
        "link_ingresso": e.link_ingresso,
        "artistas": list(e.artistas),
        "artistas_norm": normalizar_artistas(e.artistas),
        "festival": e.festival,
        "status": e.status_indicado or "ativo",
    }


def _vazio(v: Any) -> bool:
    return v is None or v == [] or (isinstance(v, str) and not v.strip())


def _texto(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, list):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def _validar(d: Decisao, candidatos: list[Evento]) -> Evento | None:
    invalidos = [c for c in d.mudancas if c not in CAMPOS_PERMITIDOS]
    if invalidos:
        raise DecisaoInvalida(f"campos não permitidos: {invalidos}")
    if not evento_id_valido(d, candidatos):
        raise DecisaoInvalida(f"evento_id {d.evento_id!r} fora dos candidatos")
    if d.decisao == "NOVO":
        return None
    return next(c for c in candidatos if c.id == d.evento_id)


def _vincular(s: Session, ev: Evento, post: Post, decisao: str) -> None:
    s.execute(
        insert(EventoFonte)
        .values(evento_id=ev.id, post_id=post.id, decisao=decisao)
        .on_conflict_do_nothing(constraint="uq_evento_fontes_evento_post")
    )


def _alterar(
    s: Session, ev: Evento, campo: str, novo: dict[str, Any], post: Post | None,
    motivo: str | None,
) -> None:
    """Grava `campo` (e sua coluna derivada) se o valor novo nao for vazio e
    diferir do atual, com uma RevisaoEvento."""
    valor = novo[campo]
    if _vazio(valor):
        return
    anterior = getattr(ev, campo)
    if anterior == valor:
        return
    if campo == "inicio" and _so_perde_horario(ev, novo):
        return
    setattr(ev, campo, valor)
    if campo in _DERIVADAS:
        derivada = _DERIVADAS[campo]
        setattr(ev, derivada, novo[derivada])
    s.add(
        RevisaoEvento(
            evento_id=ev.id, post_id=post.id if post else None, campo=campo,
            valor_anterior=_texto(anterior), valor_novo=_texto(valor), motivo=motivo,
        )
    )


def _so_perde_horario(ev: Evento, novo: dict[str, Any]) -> bool:
    """O post traz só a data (sem hora), a mesma do evento que já tem horário:
    trocar `inicio` apagaria a hora conhecida."""
    return (
        ev.hora_definida
        and not novo["hora_definida"]
        and ev.inicio.astimezone(FUSO).date() == novo["inicio"].astimezone(FUSO).date()
    )


def _so_acrescenta_horario(ev: Evento, novo: dict[str, Any]) -> bool:
    """O evento tem só a data e o post traz a hora no mesmo dia: é dado que faltava."""
    return (
        not ev.hora_definida
        and novo["hora_definida"]
        and ev.inicio.astimezone(FUSO).date() == novo["inicio"].astimezone(FUSO).date()
    )


def _falta(ev: Evento, campo: str, novo: dict[str, Any]) -> bool:
    if campo == "inicio":
        return _so_acrescenta_horario(ev, novo)
    return _vazio(getattr(ev, campo))


def _so_preenche(ev: Evento, mudancas: list[str], novo: dict[str, Any], status: str | None) -> bool:
    """ATUALIZACAO que só preenche o que faltava no evento (ou lista campos que o post
    nem informa, que `_alterar` ignora) é, na verdade, DUPLICADO."""
    return (status is None or status == ev.status) and all(
        _falta(ev, c, novo) or _vazio(novo[c]) for c in mudancas
    )


def _ja_criado_pelo_post(
    s: Session, candidatos: list[Evento], post: Post, inicio: datetime
) -> Evento | None:
    """R23: reaplicar o NOVO de um post cujo evento ja existe entre os candidatos."""
    mesmos = [c for c in candidatos if c.inicio == inicio]
    if not mesmos:
        return None
    vinculados = set(
        s.scalars(
            select(EventoFonte.evento_id).where(
                EventoFonte.post_id == post.id,
                EventoFonte.evento_id.in_([c.id for c in mesmos]),
            )
        )
    )
    return next((c for c in mesmos if c.id in vinculados), None)


def _duplicado(
    s: Session, ev: Evento, novo: dict[str, Any], post: Post, motivo: str | None
) -> None:
    for campo in _ORDEM:
        if _falta(ev, campo, novo):
            _alterar(s, ev, campo, novo, post, motivo)
    s.flush()
    _vincular(s, ev, post, "duplicado")


def aplicar(
    s: Session,
    e: EventoExtraido,
    d: Decisao,
    candidatos: list[Evento],
    post: Post,
    *,
    motivo: str | None = None,
) -> Evento:
    """Aplica a decisao num savepoint (R24): tudo ou nada; nunca faz commit."""
    alvo = _validar(d, candidatos)
    motivo = motivo or d.motivo
    novo = campos_do_evento(e)
    decisao = d.decisao
    if (
        alvo is not None
        and alvo.inicio != novo["inicio"]
        and alvo.id in eventos_do_post(s, post, [alvo])
    ):
        # R30: o alvo veio deste mesmo post com outro início (agenda mensal, flyer):
        # é outro evento do post, não o mesmo remarcado.
        log.warning(
            "post %s: %s contra o evento %s do mesmo post com outro início; aplicado como NOVO",
            post.id, decisao, alvo.id,
        )
        decisao, alvo = "NOVO", None
    # Em DUPLICADO/ATUALIZACAO, sem status_indicado o post nao informa status:
    # None (ignorado), nunca "ativo" (o default vale so para criar um evento).
    atualizacao = {**novo, "status": e.status_indicado}
    if decisao == "ATUALIZACAO" and alvo is not None and _so_preenche(
        alvo, d.mudancas, novo, e.status_indicado
    ):
        decisao = "DUPLICADO"

    with s.begin_nested():
        if decisao == "NOVO":
            existente = _ja_criado_pelo_post(s, candidatos, post, novo["inicio"])
            if existente is not None:
                _duplicado(s, existente, atualizacao, post, motivo)
                return existente
            ev = Evento(**novo)
            s.add(ev)
            s.flush()
            _vincular(s, ev, post, "novo")
            return ev

        assert alvo is not None
        if decisao == "DUPLICADO":
            _duplicado(s, alvo, atualizacao, post, motivo)
            return alvo

        campos = set(d.mudancas)
        if e.status_indicado is not None and e.status_indicado != alvo.status:
            campos.add("status")
        for campo in _ORDEM:
            if campo in campos:
                _alterar(s, alvo, campo, atualizacao, post, motivo)
        s.flush()
        _vincular(s, alvo, post, "atualizacao")
        return alvo
