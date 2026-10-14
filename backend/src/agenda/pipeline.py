"""Handlers dos jobs do pipeline: coletar_perfil -> extrair_post -> reconciliar_post.

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
from agenda.coleta.servico import baixar_url, coletar_perfil
from agenda.extracao.extrator import Extrator, Uso
from agenda.extracao.regras import agrupar_festivais, filtrar_validos
from agenda.extracao.schema import ExtracaoPost
from agenda.jobs import enfileirar
from agenda.models import Job, Post
from agenda.reconciliacao.aplicar import aplicar
from agenda.reconciliacao.candidatos import buscar_candidatos
from agenda.reconciliacao.decisao import Reconciliador
from agenda.storage import Storage

# Chave fixa do pg_advisory_xact_lock que serializa a reconciliação (R11).
LOCK_RECONCILIACAO = 7_310_001


def _agora_utc() -> datetime:
    return datetime.now(UTC)


@dataclass
class Dependencias:
    coletor: Coletor
    storage: Storage
    extrator: Extrator
    reconciliador: Reconciliador
    baixar: Callable[[str], bytes] = baixar_url
    relogio: Callable[[], datetime] = field(default=_agora_utc)
    intervalo_coleta_horas: int | None = None  # None: Settings.intervalo_coleta_horas


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


def tratar_coletar_perfil(s: Session, job: Job, deps: Dependencias) -> None:
    coletar_perfil(
        s,
        job.payload["perfil_id"],
        deps.coletor,
        deps.storage,
        agora=deps.relogio(),
        baixar=deps.baixar,
        intervalo_horas=deps.intervalo_coleta_horas,
    )


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
    for e in eventos:
        candidatos = buscar_candidatos(s, e, agora=agora)
        decisao, uso = deps.reconciliador.decidir(e, candidatos, post)
        somar_uso(post, uso)
        aplicar(s, e, decisao, candidatos, post)
    post.status = "reconciliado"
    post.erro_msg = None
    s.flush()


HANDLERS: dict[str, Callable[[Session, Job, Dependencias], None]] = {
    "coletar_perfil": tratar_coletar_perfil,
    "extrair_post": tratar_extrair_post,
    "reconciliar_post": tratar_reconciliar_post,
}
