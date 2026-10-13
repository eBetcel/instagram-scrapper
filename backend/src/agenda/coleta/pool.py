import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from agenda.coleta.base import SemContasDisponiveis
from agenda.models import ContaColeta

JANELA = timedelta(hours=1)


def cifrar_sessao(sessao: dict, chave: str) -> str:
    return Fernet(chave.encode()).encrypt(json.dumps(sessao).encode()).decode()


def decifrar_sessao(token: str, chave: str) -> dict:
    return json.loads(Fernet(chave.encode()).decrypt(token.encode()))


class PoolContas:
    """Pool de contas de coleta, estado compartilhado entre workers.

    Cada operação usa uma sessão curta da fábrica e dá commit. `obter` devolve
    o ContaColeta já destacado (expunge) da sessão, portanto utilizável depois
    que ela fecha (atributos carregados; sem lazy loading).
    """

    def __init__(self, session_factory: Callable[[], Session], limite_por_hora: int):
        self._factory = session_factory
        self.limite_por_hora = limite_por_hora

    def obter(self, agora: datetime | None = None) -> ContaColeta:
        agora = agora or datetime.now(UTC)
        with self._factory() as s:
            candidatas = s.scalars(
                select(ContaColeta)
                .where(
                    or_(
                        ContaColeta.status == "ativa",
                        (ContaColeta.status == "bloqueada") & (ContaColeta.bloqueada_ate <= agora),
                    ),
                    or_(ContaColeta.bloqueada_ate.is_(None), ContaColeta.bloqueada_ate <= agora),
                )
                .order_by(ContaColeta.ultimo_uso_em.asc().nulls_first(), ContaColeta.id)
                .with_for_update(skip_locked=True)
            ).all()
            for conta in candidatas:
                if conta.janela_inicio is None or agora - conta.janela_inicio >= JANELA:
                    conta.janela_inicio = agora
                    conta.usos_janela = 0
                if conta.usos_janela >= self.limite_por_hora:
                    continue
                conta.status = "ativa"
                conta.bloqueada_ate = None
                conta.usos_janela += 1
                conta.ultimo_uso_em = agora
                s.commit()
                s.refresh(conta)
                s.expunge(conta)
                return conta
            s.commit()  # persiste resets de janela de contas puladas
        raise SemContasDisponiveis()

    def marcar_bloqueada(self, conta: ContaColeta, ate: datetime) -> None:
        with self._factory() as s:
            row = s.get(ContaColeta, conta.id)
            row.status = "bloqueada"
            row.bloqueada_ate = ate
            s.commit()
