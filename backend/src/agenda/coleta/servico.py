"""Serviço de coleta incremental e agendador.

Nenhuma função faz commit: a transação pertence a quem chama.
"""

import random
import urllib.request
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from agenda.coleta.base import (
    MAX_FIXADOS,
    Coletor,
    PerfilInexistente,
    PerfilPrivado,
)
from agenda.config import get_settings
from agenda.jobs import enfileirar, reativar_ou_enfileirar
from agenda.models import GrupoPerfil, Perfil, Post
from agenda.storage import Storage

JANELA_PRIMEIRA_COLETA = timedelta(days=30)
JITTER_MAXIMO_SEGUNDOS = 30 * 60


def baixar_url(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def _dono(s: Session, shortcode: str) -> int | None:
    """perfil_id que salvou o shortcode, ou None se ainda não existe."""
    return s.scalar(select(Post.perfil_id).where(Post.shortcode == shortcode))


def coletar_perfil(
    s: Session,
    perfil_id: int,
    coletor: Coletor,
    storage: Storage,
    *,
    agora: datetime,
    baixar: Callable[[str], bytes] = baixar_url,
    intervalo_horas: int | None = None,
) -> int:
    """Coleta posts novos do perfil e devolve quantos foram salvos.

    Os MAX_FIXADOS primeiros posts (ou os marcados `fixado`) não disparam as regras
    de parada. Posts anteriores a `desde` nunca são salvos. ContaBloqueada e
    SemContasDisponiveis propagam sem atualizar as datas de coleta; erros de
    download também propagam (o job é repetido).
    """
    perfil = s.get(Perfil, perfil_id)
    if perfil is None:
        raise ValueError(f"perfil {perfil_id} não existe")
    desde = perfil.ultima_coleta_em or agora - JANELA_PRIMEIRA_COLETA
    if intervalo_horas is None:
        intervalo_horas = get_settings().intervalo_coleta_horas

    novos = 0
    try:
        for i, p in enumerate(coletor.posts_desde(perfil.username, desde)):
            ancora = p.fixado or i < MAX_FIXADOS
            if p.publicado_em < desde:
                if ancora:
                    continue
                break
            dono = _dono(s, p.shortcode)
            if dono is not None:
                # Só um post já salvo por ESTE perfil marca o ponto de parada; o de
                # outro perfil (collab) é só pulado. Atribuição multi-perfil: Fatia 2.
                if ancora or dono != perfil.id:
                    continue
                break
            if _salvar_post(s, perfil, p, storage, baixar):
                novos += 1
    except PerfilPrivado:
        perfil.status = "privado"
        s.flush()
        return 0
    except PerfilInexistente:
        perfil.status = "inexistente"
        s.flush()
        return 0

    perfil.ultima_coleta_em = agora
    perfil.proxima_coleta_em = agora + timedelta(hours=intervalo_horas)
    s.flush()
    return novos


def _salvar_post(s: Session, perfil: Perfil, p, storage: Storage, baixar) -> bool:
    # Baixa antes de inserir: falha de download não deixa post parcial.
    dados = [baixar(url) for url in p.urls_imagens]
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


def agendar_coletas(s: Session, agora: datetime, *, rng: random.Random | None = None) -> int:
    """Garante coletar_perfil para perfis ativos devidos (proxima_coleta_em NULL conta).

    Perfil nunca coletado tem prioridade (`executar_em = agora`, sem jitter); os
    demais recebem jitter de até 30 min. Um job de coleta morto ('erro') é
    reativado — senão a chave o bloquearia para sempre. Devolve quantos jobs
    foram criados ou reativados.
    """
    rng = rng or random.Random()
    perfis = s.execute(
        select(Perfil.id, Perfil.ultima_coleta_em)
        .where(
            Perfil.status == "ativo",
            (Perfil.proxima_coleta_em.is_(None)) | (Perfil.proxima_coleta_em <= agora),
            # Só quem algum grupo acompanha, ou cadastrado pela CLI.
            Perfil.fixo | select(GrupoPerfil.perfil_id).where(GrupoPerfil.perfil_id == Perfil.id).exists(),
        )
        .order_by(Perfil.id)
    ).all()
    enfileirados = 0
    for pid, ultima in perfis:
        if ultima is None:
            executar_em = agora
        else:
            executar_em = agora + timedelta(seconds=rng.uniform(0, JITTER_MAXIMO_SEGUNDOS))
        r = reativar_ou_enfileirar(
            s, "coletar_perfil", {"perfil_id": pid}, f"coletar:{pid}", executar_em=executar_em
        )
        if r != "existente":
            enfileirados += 1
    return enfileirados
