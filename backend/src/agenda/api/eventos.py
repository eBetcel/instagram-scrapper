"""Agenda da pessoa, detalhe de evento e imagens dos flyers."""

import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from agenda.api.consultas import eventos_da_agenda, resumir
from agenda.api.deps import deps_api, sessao_db, usuario_atual
from agenda.api.esquemas import EventoDetalhe, FonteSaida, RevisaoSaida
from agenda.extracao.regras import FUSO
from agenda.models import Evento, EventoFonte, Perfil, Post, RevisaoEvento, Usuario

DIAS_PADRAO = 7
_SHORTCODE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

rotas = APIRouter(prefix="/api")


@rotas.get("/agenda")
def agenda(
    de: date | None = None, ate: date | None = None, grupo: str | None = None,
    categoria: str | None = None, gratuito: bool = False,
    s: Session = Depends(sessao_db), u: Usuario = Depends(usuario_atual), deps=Depends(deps_api),
) -> dict:
    agora = deps.relogio()
    de = de or agora.astimezone(FUSO).date()
    ate = ate or de + timedelta(days=DIAS_PADRAO)
    eventos = eventos_da_agenda(s, u.id, de, ate, grupo=grupo, categoria=categoria, gratuito=gratuito)
    return {"eventos": resumir(s, eventos, agora)}


@rotas.get("/eventos/{evento_id}")
def detalhe(evento_id: int, s: Session = Depends(sessao_db), deps=Depends(deps_api)) -> EventoDetalhe:
    e = s.get(Evento, evento_id)
    if e is None:
        raise HTTPException(404, "Evento não encontrado")
    [resumo] = resumir(s, [e], deps.relogio())
    fontes = [
        FonteSaida(username=username, shortcode=sc, url_instagram=f"https://www.instagram.com/p/{sc}/",
                   publicado_em=publicado_em, decisao=decisao)
        for username, sc, publicado_em, decisao in s.execute(
            select(Perfil.username, Post.shortcode, Post.publicado_em, EventoFonte.decisao)
            .join(Post, Post.id == EventoFonte.post_id).join(Perfil, Perfil.id == Post.perfil_id)
            .where(EventoFonte.evento_id == e.id).order_by(Post.publicado_em, Post.id)
        )
    ]
    revisoes = [
        RevisaoSaida(campo=r.campo, valor_anterior=r.valor_anterior, valor_novo=r.valor_novo,
                     motivo=r.motivo, criado_em=r.criado_em)
        for r in s.scalars(select(RevisaoEvento).where(RevisaoEvento.evento_id == e.id)
                           .order_by(RevisaoEvento.criado_em, RevisaoEvento.id))
    ]
    return EventoDetalhe(**resumo.model_dump(), descricao=e.descricao, endereco=e.endereco,
                         fontes=fontes, revisoes=revisoes)


@rotas.get("/posts/{shortcode}/imagens/{n}")
def imagem(shortcode: str, n: int, deps=Depends(deps_api)) -> Response:
    if not _SHORTCODE.match(shortcode) or n < 0:
        raise HTTPException(404, "Imagem não encontrada")
    try:
        dados = deps.storage.ler(f"posts/{shortcode}/{n}.jpg")
    except Exception:  # KeyError (memória) ou NoSuchKey (S3)
        raise HTTPException(404, "Imagem não encontrada") from None
    return Response(dados, media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"})
