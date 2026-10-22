"""Handlers dos jobs do pipeline: extrair_post -> reconciliar_post.

Cada handler roda na transação do worker (junto com `concluir`) e nunca faz commit.
Os handlers são idempotentes: trabalho já feito é ignorado.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agenda.coleta.base import Coletor
from agenda.coleta.servico import baixar_url, coletar_lote
from agenda.extracao.extrator import Extrator, Uso
from agenda.extracao.regras import agrupar_festivais, filtrar_validos
from agenda.extracao.schema import EventoExtraido, ExtracaoPost
from agenda.jobs import enfileirar
from agenda.models import Evento, EventoFonte, Job, Post
from agenda.reconciliacao.aplicar import aplicar, campos_do_evento
from agenda.reconciliacao.candidatos import buscar_candidatos
from agenda.reconciliacao.decisao import Reconciliador, eventos_do_post
from agenda.reconciliacao.fusao import deduplicar
from agenda.reconciliacao.identidade import pares_fortes
from agenda.storage import Storage

# Chave fixa do pg_advisory_xact_lock que serializa a reconciliação (R11).
LOCK_RECONCILIACAO = 7_310_001


def _agora_utc() -> datetime:
    return datetime.now(UTC)


@dataclass
class Dependencias:
    storage: Storage
    extrator: Extrator
    reconciliador: Reconciliador
    coletor: Coletor
    preco_por_post: Decimal = Decimal("0.0017")
    baixar: Callable[[str], bytes] = baixar_url
    relogio: Callable[[], datetime] = field(default=_agora_utc)


def somar_uso(post: Post, uso: Uso | None) -> None:
    """Acumula tokens e custo no post (NULL conta como 0)."""
    if uso is None:
        return
    post.tokens_entrada = (post.tokens_entrada or 0) + uso.tokens_entrada
    post.tokens_saida = (post.tokens_saida or 0) + uso.tokens_saida
    post.custo_estimado = (post.custo_estimado or Decimal(0)) + uso.custo


def _post(s: Session, job: Job) -> Post:
    post = s.get(Post, job.payload["post_id"])
    if post is None:
        raise ValueError(f"post {job.payload['post_id']} não existe")
    return post


def tratar_extrair_post(s: Session, job: Job, deps: Dependencias) -> None:
    post = _post(s, job)
    if post.status != "pendente":
        return
    imagens = [deps.storage.ler(chave) for chave in post.imagens]
    publicado_em = post.publicado_em or deps.relogio()
    resultado = deps.extrator.extrair(post.legenda or "", imagens, post.perfil.username, publicado_em)
    post.extracao = resultado.extracao.model_dump(mode="json")
    post.modelo_extracao = resultado.uso.modelo
    somar_uso(post, resultado.uso)
    post.status = "extraido"
    post.erro_msg = None
    s.flush()
    enfileirar(s, "reconciliar_post", {"post_id": post.id}, chave=f"reconciliar:{post.id}")


def par_forte(
    s: Session, e: EventoExtraido, candidatos: list[Evento], post: Post
) -> Evento | None:
    """Candidato de outro post que é, deterministicamente, o mesmo evento; com mais de
    um, o de mais fontes (empate: menor id)."""
    do_post = eventos_do_post(s, post, candidatos)
    pares = pares_fortes(Evento(**campos_do_evento(e)), [c for c in candidatos if c.id not in do_post])
    if not pares:
        return None
    fontes = dict(
        s.execute(
            select(EventoFonte.evento_id, func.count())
            .where(EventoFonte.evento_id.in_([c.id for c in pares]))
            .group_by(EventoFonte.evento_id)
        ).all()
    )
    return min(pares, key=lambda c: (-fontes.get(c.id, 0), c.id))


def tratar_reconciliar_post(s: Session, job: Job, deps: Dependencias) -> None:
    """Reconcilia todos os eventos válidos do post na transação do job (R26)."""
    s.execute(select(func.pg_advisory_xact_lock(LOCK_RECONCILIACAO)))
    post = _post(s, job)
    s.refresh(post)  # estado visto após obter o lock
    if post.status == "reconciliado":
        return
    if post.status != "extraido" or post.extracao is None:
        raise ValueError(f"post {post.id} com status {post.status!r} não pode ser reconciliado")
    agora = deps.relogio()
    eventos = agrupar_festivais(
        filtrar_validos(ExtracaoPost.model_validate(post.extracao).eventos, agora)
    )
    tocados = []
    for e in eventos:
        candidatos = buscar_candidatos(s, e, agora=agora)
        par = par_forte(s, e, candidatos, post)
        if par is not None:
            candidatos = [par]
        decisao, uso = deps.reconciliador.decidir(
            e, candidatos, post, exigir_candidato=par is not None
        )
        somar_uso(post, uso)
        tocados.append(aplicar(s, e, decisao, candidatos, post))
    deduplicar(s, agora=agora, eventos=tocados)
    post.status = "reconciliado"
    post.erro_msg = None
    s.flush()


def tratar_coletar_lote(s: Session, job: Job, deps: Dependencias) -> None:
    coletar_lote(
        s,
        job.payload["lote_id"],
        deps.coletor,
        deps.storage,
        agora=deps.relogio(),
        baixar=deps.baixar,
        preco_por_post=deps.preco_por_post,
    )


HANDLERS: dict[str, Callable[[Session, Job, Dependencias], None]] = {
    "coletar_lote": tratar_coletar_lote,
    "extrair_post": tratar_extrair_post,
    "reconciliar_post": tratar_reconciliar_post,
}
