"""Serviço de coleta.

Nenhuma função faz commit: a transação pertence a quem chama.
"""

import logging
import urllib.request
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from agenda.coleta.apify import classificar_erro
from agenda.coleta.base import Coletor, PostColetado, ResultadoLote
from agenda.jobs import enfileirar
from agenda.models import LoteColeta, Perfil, Post
from agenda.storage import Storage

log = logging.getLogger(__name__)

PERFIS_POR_EXECUCAO = 50


def baixar_url(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def coletar_lote(
    s: Session,
    lote_id: int,
    coletor: Coletor,
    storage: Storage,
    *,
    agora: datetime,
    baixar: Callable[[str], bytes] = baixar_url,
    preco_por_post: Decimal,
) -> int:
    """Coleta e grava os posts do lote; devolve quantos posts novos foram salvos.

    Falhas do coletor propagam (o worker decide); o lote fica `executando`.
    """
    lote = s.get(LoteColeta, lote_id)
    if lote is None:
        raise ValueError(f"lote {lote_id} não existe")
    if lote.status == "concluido":
        return 0
    lote.status = "executando"
    s.flush()

    perfis = {
        p.username: p
        for p in s.scalars(select(Perfil).where(Perfil.username.in_(lote.perfis)))
    }
    usernames = []
    for u in lote.perfis:
        if u in perfis:
            usernames.append(u)
        else:
            log.warning("lote %s: perfil @%s não existe; ignorado", lote.id, u)

    resultado = ResultadoLote()
    for i in range(0, len(usernames), PERFIS_POR_EXECUCAO):
        parte = coletor.coletar(
            usernames[i : i + PERFIS_POR_EXECUCAO], janela=lote.janela, limite=lote.limite
        )
        resultado.posts.extend(parte.posts)
        resultado.erros.update(parte.erros)
        resultado.run_ids.extend(parte.run_ids)

    novos = 0
    vistos: set[str] = set()
    existentes = set(
        s.scalars(
            select(Post.shortcode).where(
                Post.shortcode.in_([p.shortcode for p in resultado.posts])
            )
        )
    )
    for p in resultado.posts:
        if p.shortcode in existentes or p.shortcode in vistos:
            continue
        vistos.add(p.shortcode)
        perfil = perfis.get(p.perfil)
        if perfil is None:
            log.warning("lote %s: post %s de perfil fora do lote (@%s)", lote.id, p.shortcode, p.perfil)
            continue
        if _salvar_post(s, perfil, p, storage, baixar):
            novos += 1

    for username, msg in resultado.erros.items():
        perfil = perfis.get(username)
        if perfil is None:
            continue
        if classificar_erro(msg) == "inexistente":
            perfil.status = "inexistente"
        else:
            log.warning("lote %s: erro ao coletar @%s: %s", lote.id, username, msg)
    for username in usernames:
        if username not in resultado.erros:
            perfis[username].ultima_coleta_em = agora

    lote.posts = len(resultado.posts)
    lote.posts_novos = novos
    lote.custo_estimado = (Decimal(lote.posts) * preco_por_post).quantize(Decimal("0.0001"))
    lote.run_ids = resultado.run_ids
    lote.status = "concluido"
    lote.concluido_em = agora
    s.flush()
    return novos


def _salvar_post(s: Session, perfil: Perfil, p: PostColetado, storage: Storage, baixar) -> bool:
    dados: list[bytes] = []
    for url in p.urls_imagens:
        try:
            dados.append(baixar(url))
        except Exception as e:
            log.warning("post %s: imagem não baixada (%s): %s", p.shortcode, url, e)
    chaves = [f"posts/{p.shortcode}/{n}.jpg" for n in range(len(dados))]
    post_id = s.execute(
        insert(Post)
        .values(
            perfil_id=perfil.id,
            shortcode=p.shortcode,
            legenda=p.legenda,
            publicado_em=p.publicado_em,
            imagens=chaves,
            status="pendente",
        )
        .on_conflict_do_nothing(index_elements=["shortcode"])
        .returning(Post.id)
    ).scalar_one_or_none()
    if post_id is None:
        return False
    for chave, d in zip(chaves, dados):
        storage.salvar(chave, d, "image/jpeg")
    enfileirar(s, "extrair_post", {"post_id": post_id}, chave=f"extrair:{post_id}")
    return True
