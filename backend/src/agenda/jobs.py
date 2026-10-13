"""Fila de jobs no Postgres.

Nenhuma função faz commit: a transação pertence a quem chama. O worker faz commit
da reserva antes de executar o handler; `executar_em` de um job 'executando' marca
o início da execução, e `recuperar_travados` devolve à fila os que passaram do limite
(worker morto no meio).
"""

from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from agenda.models import Job

_BACKOFF_BASE_SEGUNDOS = 30


def enfileirar(
    s: Session,
    tipo: str,
    payload: dict,
    *,
    executar_em: datetime | None = None,
    max_tentativas: int = 5,
    chave: str | None = None,
) -> Job | None:
    """Enfileira um job. Com `chave`, é idempotente: devolve None se já há job não concluído."""
    valores = {"tipo": tipo, "payload": payload, "max_tentativas": max_tentativas, "chave": chave}
    if executar_em is not None:
        valores["executar_em"] = executar_em
    stmt = insert(Job).values(**valores)
    if chave is not None:
        stmt = stmt.on_conflict_do_nothing(
            index_elements=[Job.tipo, Job.chave],
            index_where=(Job.chave.is_not(None)) & (Job.status != "concluido"),
        )
    return s.scalars(
        stmt.returning(Job), execution_options={"populate_existing": True}
    ).one_or_none()


def reservar(s: Session, tipos: list[str]) -> Job | None:
    """Pega o próximo job pronto dos `tipos` e o marca como executando (SKIP LOCKED),
    com `executar_em = now()` (início da execução)."""
    job = s.scalars(
        select(Job)
        .where(Job.tipo.in_(tipos), Job.status == "pendente", Job.executar_em <= func.now())
        .order_by(Job.executar_em, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).one_or_none()
    if job is not None:
        job.status = "executando"
        job.executar_em = func.now()
        s.flush()
    return job


def concluir(s: Session, job: Job) -> None:
    job.status = "concluido"
    s.flush()


def falhar(s: Session, job: Job, erro: str) -> None:
    """Registra falha: reagenda com backoff 2**tentativas * 30s ou vira 'erro' ao esgotar."""
    job.tentativas += 1
    job.erro_msg = erro
    if job.tentativas >= job.max_tentativas:
        job.status = "erro"
    else:
        job.status = "pendente"
        segundos = 2**job.tentativas * _BACKOFF_BASE_SEGUNDOS
        job.executar_em = func.now() + timedelta(seconds=segundos)
    s.flush()


def falhar_definitivo(s: Session, job: Job, erro: str) -> None:
    """Falha terminal: vira 'erro' sem retentativa."""
    job.tentativas += 1
    job.erro_msg = erro
    job.status = "erro"
    s.flush()


def recuperar_travados(s: Session, limite: timedelta = timedelta(minutes=30)) -> int:
    """Devolve à fila jobs 'executando' há mais de `limite`; retorna quantos."""
    res = s.execute(
        update(Job)
        .where(Job.status == "executando", Job.executar_em < func.now() - limite)
        .values(status="pendente")
        .execution_options(synchronize_session=False)
    )
    return res.rowcount
