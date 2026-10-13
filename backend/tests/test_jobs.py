from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from agenda.jobs import (
    concluir,
    enfileirar,
    falhar,
    falhar_definitivo,
    recuperar_travados,
    reservar,
)
from agenda.models import Job


def _agora(s: Session) -> datetime:
    return s.scalar(select(func.now()))


def test_enfileirar_cria_job_pendente(session):
    job = enfileirar(session, "coletar", {"a": 1})
    assert job is not None
    assert job.id is not None
    assert job.status == "pendente"
    assert job.payload == {"a": 1}
    assert job.tentativas == 0
    assert job.max_tentativas == 5


def test_reservar_respeita_executar_em(session):
    futuro = _agora(session) + timedelta(hours=1)
    enfileirar(session, "t_futuro", {}, executar_em=futuro)
    assert reservar(session, ["t_futuro"]) is None

    passado = _agora(session) - timedelta(minutes=1)
    enfileirar(session, "t_passado", {}, executar_em=passado)
    job = reservar(session, ["t_passado"])
    assert job is not None
    assert job.status == "executando"


def test_reservar_filtra_por_tipo_e_status(session):
    enfileirar(session, "outro", {})
    assert reservar(session, ["t_x"]) is None
    enfileirar(session, "t_x", {})
    assert reservar(session, ["t_x"]) is not None
    assert reservar(session, ["t_x"]) is None  # já executando


def test_reservar_nao_entrega_o_mesmo_job_a_duas_sessoes(engine):
    with Session(engine) as s0:
        job = enfileirar(s0, "t_conc", {})
        s0.commit()
        job_id = job.id
    s1 = Session(engine)
    s2 = Session(engine)
    try:
        r1 = reservar(s1, ["t_conc"])  # transação de s1 segue aberta (lock)
        assert r1 is not None and r1.id == job_id
        assert reservar(s2, ["t_conc"]) is None
    finally:
        s1.rollback()
        s2.rollback()
        s1.close()
        s2.close()
        with Session(engine) as s0:
            s0.execute(delete(Job).where(Job.id == job_id))
            s0.commit()


def test_concluir_marca_concluido(session):
    enfileirar(session, "t_c", {})
    job = reservar(session, ["t_c"])
    concluir(session, job)
    assert job.status == "concluido"


def test_falhar_aplica_backoff_exponencial(session):
    enfileirar(session, "t_b", {})
    job = reservar(session, ["t_b"])
    falhar(session, job, "boom")
    session.refresh(job)
    agora = _agora(session)  # now() é fixo dentro da transação
    assert job.tentativas == 1
    assert job.status == "pendente"
    assert job.erro_msg == "boom"
    assert job.executar_em == agora + timedelta(seconds=60)

    job.executar_em = agora - timedelta(seconds=1)
    session.flush()
    job = reservar(session, ["t_b"])
    falhar(session, job, "boom2")
    session.refresh(job)
    assert job.tentativas == 2
    assert job.executar_em == agora + timedelta(seconds=120)
    assert job.erro_msg == "boom2"


def test_falhar_esgota_tentativas_vira_erro(session):
    job = enfileirar(session, "t_e", {}, max_tentativas=1)
    job = reservar(session, ["t_e"])
    antes = job.executar_em
    falhar(session, job, "fim")
    session.refresh(job)
    assert job.status == "erro"
    assert job.tentativas == 1
    assert job.erro_msg == "fim"
    assert job.executar_em == antes
    assert reservar(session, ["t_e"]) is None


def test_enfileirar_com_chave_e_idempotente(session):
    a = enfileirar(session, "t_k", {}, chave="k1")
    b = enfileirar(session, "t_k", {}, chave="k1")
    assert a is not None
    assert b is None
    assert session.scalar(select(func.count()).select_from(Job).where(Job.tipo == "t_k")) == 1
    # outra chave / outro tipo não colidem
    assert enfileirar(session, "t_k", {}, chave="k2") is not None
    assert enfileirar(session, "t_k2", {}, chave="k1") is not None


def test_enfileirar_com_chave_apos_concluido_cria_novo(session):
    a = enfileirar(session, "t_r", {}, chave="k")
    job = reservar(session, ["t_r"])
    concluir(session, job)
    b = enfileirar(session, "t_r", {}, chave="k")
    assert b is not None and b.id != a.id


def test_enfileirar_sem_chave_nunca_deduplica(session):
    a = enfileirar(session, "t_n", {})
    b = enfileirar(session, "t_n", {})
    assert a is not None and b is not None and a.id != b.id


def test_reservar_marca_executar_em_com_agora(session):
    passado = _agora(session) - timedelta(hours=2)
    enfileirar(session, "t_res", {}, executar_em=passado)
    job = reservar(session, ["t_res"])
    session.refresh(job)
    assert job.executar_em == _agora(session)


def test_recuperar_travados_volta_executando_antigo_para_pendente(session):
    agora = _agora(session)
    enfileirar(session, "t_trav", {})
    travado = reservar(session, ["t_trav"])
    travado.executar_em = agora - timedelta(minutes=31)
    enfileirar(session, "t_trav", {})
    recente = reservar(session, ["t_trav"])
    recente.executar_em = agora - timedelta(minutes=29)
    session.flush()

    assert recuperar_travados(session) == 1
    session.refresh(travado)
    session.refresh(recente)
    assert travado.status == "pendente"
    assert recente.status == "executando"
    assert recuperar_travados(session, timedelta(minutes=10)) == 1
    session.refresh(recente)
    assert recente.status == "pendente"


def test_falhar_definitivo_vira_erro_sem_retentativa(session):
    enfileirar(session, "t_def", {})
    job = reservar(session, ["t_def"])
    falhar_definitivo(session, job, "inválida")
    session.refresh(job)
    assert job.status == "erro"
    assert job.tentativas == 1
    assert job.erro_msg == "inválida"
    assert reservar(session, ["t_def"]) is None


def test_reativar_ou_enfileirar_cobre_novo_reativado_existente(session):
    from agenda.jobs import reativar_ou_enfileirar

    assert reativar_ou_enfileirar(session, "t", {"a": 1}, "k1") == "novo"
    assert reativar_ou_enfileirar(session, "t", {"a": 1}, "k1") == "existente"

    job = session.scalars(select(Job).where(Job.chave == "k1")).one()
    job.status, job.tentativas, job.erro_msg = "erro", 5, "boom"
    session.flush()
    assert reativar_ou_enfileirar(session, "t", {"a": 1}, "k1") == "reativado"
    session.refresh(job)
    assert (job.status, job.tentativas, job.erro_msg) == ("pendente", 0, None)
    assert job.executar_em <= _agora(session)

    job.status = "executando"
    session.flush()
    assert reativar_ou_enfileirar(session, "t", {"a": 1}, "k1") == "existente"
    assert job.status == "executando"

    job.status = "concluido"
    session.flush()
    assert reativar_ou_enfileirar(session, "t", {"a": 1}, "k1") == "novo"
