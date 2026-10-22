"""Loop do worker.

A reserva do job é confirmada numa transação própria (R14); o handler roda em outra,
junto com `concluir` (R27). Em falha, essa transação é desfeita e uma terceira
registra o erro. O worker de reconciliação é um único processo com
`tipos=["reconciliar_post"]`.
"""

import logging
import time
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from agenda.coleta.apify import ApifyRecusou
from agenda.coleta.servico import agendar_lotes
from agenda.db import session_scope
from agenda.extracao.extrator import RespostaInvalida
from agenda.jobs import (
    concluir,
    falhar,
    falhar_definitivo,
    recuperar_travados,
    reservar,
)
from agenda.models import Job, LoteColeta, Post
from agenda.pipeline import HANDLERS, Dependencias, somar_uso

log = logging.getLogger(__name__)

INTERVALO_MANUTENCAO_SEGUNDOS = 5 * 60


def _manutencao(factory: sessionmaker[Session] | None, deps: Dependencias, tipos: list[str]) -> None:
    with session_scope(factory) as s:
        recuperados = recuperar_travados(s)
        if recuperados:
            log.warning("%d job(s) travado(s) devolvido(s) à fila", recuperados)
        if "coletar_lote" in tipos:
            criados = agendar_lotes(s, deps.relogio(), deps.horarios_coleta)
            if criados:
                log.info("lote(s) de coleta criado(s): %s", criados)


def _reservar(factory: sessionmaker[Session] | None, tipos: list[str]) -> int | None:
    with session_scope(factory) as s:
        job = reservar(s, tipos)
        return job.id if job is not None else None


def _marcar_post_erro(s: Session, job: Job, erro: str) -> Post | None:
    post_id = (job.payload or {}).get("post_id")
    if post_id is None:
        return None
    post = s.get(Post, post_id)
    if post is not None:
        post.status = "erro"
        post.erro_msg = erro
    return post


def _marcar_lote_erro(s: Session, job: Job, erro: str) -> None:
    """Lote de um job `coletar_lote` que terminou em erro (R12). A mensagem vem das
    exceções do cliente, que nunca incluem o token."""
    if job.tipo != "coletar_lote":
        return
    lote = s.get(LoteColeta, (job.payload or {}).get("lote_id"))
    if lote is not None:
        lote.status = "erro"
        lote.erro_msg = erro
        s.flush()


def _executar(factory: sessionmaker[Session] | None, deps: Dependencias, job_id: int) -> None:
    try:
        with session_scope(factory) as s:
            job = s.get(Job, job_id)
            handler = HANDLERS.get(job.tipo)
            if handler is None:
                erro = f"tipo de job desconhecido: {job.tipo}"
                falhar_definitivo(s, job, erro)
                log.error("job %d terminou em erro: %s", job_id, erro)
                return
            handler(s, job, deps)
            concluir(s, job)
    except RespostaInvalida as exc:
        erro = f"{type(exc).__name__}: {exc}"
        with session_scope(factory) as s:
            job = s.get(Job, job_id)
            falhar_definitivo(s, job, erro)
            post = _marcar_post_erro(s, job, erro)
            if post is not None:
                somar_uso(post, exc.uso)
                if job.tipo == "extrair_post" and exc.uso is not None:
                    post.modelo_extracao = exc.uso.modelo
            log.error("job %d (%s) terminou em erro: %s", job_id, job.tipo, erro)
    except ApifyRecusou as exc:
        erro = f"{type(exc).__name__}: {exc}"
        with session_scope(factory) as s:
            job = s.get(Job, job_id)
            falhar_definitivo(s, job, erro)
            _marcar_lote_erro(s, job, erro)
            log.error("job %d (%s) terminou em erro, sem retentativa: %s", job_id, job.tipo, erro)
    except Exception as exc:  # noqa: BLE001 - qualquer falha do handler vira retentativa
        erro = f"{type(exc).__name__}: {exc}"
        with session_scope(factory) as s:
            job = s.get(Job, job_id)
            falhar(s, job, erro)
            if job.status == "erro":
                _marcar_post_erro(s, job, erro)
                _marcar_lote_erro(s, job, erro)
                log.error(
                    "job %d (%s) terminou em erro após %d tentativa(s): %s",
                    job_id, job.tipo, job.tentativas, erro,
                )
            else:
                log.warning("job %d (%s) falhou e foi reagendado: %s", job_id, job.tipo, erro)


def rodar_worker(
    deps: Dependencias,
    tipos: list[str],
    *,
    session_factory: sessionmaker[Session] | None = None,
    uma_vez: bool = False,
    sleep: Callable[[float], None] = time.sleep,
    intervalo_ocioso: float = 5.0,
) -> int:
    """Reserva e executa jobs dos `tipos`; devolve quantos processou.

    Ao iniciar e a cada 5 minutos devolve à fila jobs travados e, se `coletar_lote`
    está nos `tipos`, cria os lotes de coleta devidos (`agendar_lotes`). Com `uma_vez`, retorna
    quando não houver job pronto; sem ele, dorme `intervalo_ocioso` e tenta de novo.
    """
    processados = 0
    ultima_manutencao: float | None = None
    while True:
        agora = time.monotonic()
        if ultima_manutencao is None or agora - ultima_manutencao >= INTERVALO_MANUTENCAO_SEGUNDOS:
            _manutencao(session_factory, deps, tipos)
            ultima_manutencao = agora
        job_id = _reservar(session_factory, tipos)
        if job_id is None:
            if uma_vez:
                return processados
            sleep(intervalo_ocioso)
            continue
        _executar(session_factory, deps, job_id)
        processados += 1

