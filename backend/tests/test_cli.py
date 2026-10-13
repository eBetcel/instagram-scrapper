"""CLI de admin. Os comandos abrem sessões por `agenda.cli.fabrica_sessoes`, que os
testes apontam para o banco do testcontainer (com commit real e TRUNCATE depois)."""

import pickle
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker
from typer.testing import CliRunner

from agenda import cli
from agenda.coleta.pool import decifrar_sessao
from agenda.jobs import enfileirar
from agenda.models import ContaColeta, Evento, EventoFonte, Job, Perfil, Post

runner = CliRunner()
TABELAS = "revisoes_evento, evento_fontes, eventos, posts, perfis, jobs, contas_coleta"


@pytest.fixture
def fabrica(engine, monkeypatch):
    def limpar():
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {TABELAS} RESTART IDENTITY CASCADE"))

    limpar()
    f = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(cli, "fabrica_sessoes", lambda: f)
    yield f
    limpar()


def invocar(*args):
    return runner.invoke(cli.app, list(args))


def usernames(fabrica):
    with fabrica() as s:
        return s.scalars(select(Perfil.username).order_by(Perfil.id)).all()


def test_perfil_adicionar_normaliza_username(fabrica):
    r = invocar("perfil-adicionar", "  @Casa.Azul_SP ")
    assert r.exit_code == 0, r.output
    assert usernames(fabrica) == ["casa.azul_sp"]
    with fabrica() as s:
        p = s.scalars(select(Perfil)).one()
        assert p.proxima_coleta_em is not None
        assert p.proxima_coleta_em <= datetime.now(UTC)


def test_perfil_adicionar_e_idempotente(fabrica):
    assert invocar("perfil-adicionar", "casa").exit_code == 0
    r = invocar("perfil-adicionar", "@CASA")
    assert r.exit_code == 0
    assert "já existe" in r.output
    assert usernames(fabrica) == ["casa"]


@pytest.mark.parametrize("ruim", ["", "@", "com espaco", "a/b", "x" * 31, "açaí"])
def test_perfil_adicionar_rejeita_username_invalido(fabrica, ruim):
    r = invocar("perfil-adicionar", ruim)
    assert r.exit_code != 0
    assert usernames(fabrica) == []


def test_perfil_listar(fabrica):
    invocar("perfil-adicionar", "casa")
    invocar("perfil-adicionar", "bar")
    r = invocar("perfil-listar")
    assert r.exit_code == 0
    assert "casa" in r.output and "bar" in r.output


def test_coletar_enfileira_e_adianta_job_existente(fabrica):
    invocar("perfil-adicionar", "casa")
    invocar("perfil-adicionar", "bar")
    with fabrica.begin() as s:
        p = s.scalars(select(Perfil).where(Perfil.username == "casa")).one()
        p.proxima_coleta_em = datetime.now(UTC) + timedelta(hours=5)
        enfileirar(s, "coletar_perfil", {"perfil_id": p.id}, chave=f"coletar:{p.id}",
                   executar_em=datetime.now(UTC) + timedelta(hours=5))
    r = invocar("coletar", "--perfil", "@Casa")
    assert r.exit_code == 0, r.output
    with fabrica() as s:
        jobs = s.scalars(select(Job).where(Job.tipo == "coletar_perfil")).all()
        assert len(jobs) == 1  # só o do perfil pedido, sem duplicar
        assert jobs[0].executar_em <= datetime.now(UTC)
        p = s.scalars(select(Perfil).where(Perfil.username == "casa")).one()
        assert p.proxima_coleta_em <= datetime.now(UTC)


def test_coletar_sem_perfil_enfileira_todos_os_ativos(fabrica):
    invocar("perfil-adicionar", "casa")
    invocar("perfil-adicionar", "bar")
    assert invocar("coletar").exit_code == 0
    with fabrica() as s:
        assert len(s.scalars(select(Job).where(Job.tipo == "coletar_perfil")).all()) == 2


def test_coletar_perfil_inexistente_falha(fabrica):
    assert invocar("coletar", "--perfil", "nao_existe").exit_code != 0


def test_conta_adicionar_cifra_sessao(fabrica, tmp_path, monkeypatch):
    from cryptography.fernet import Fernet

    chave = Fernet.generate_key().decode()
    monkeypatch.setattr(cli, "get_settings", lambda: SimpleNamespace(chave_sessao=chave))
    arq = tmp_path / "sessao"
    arq.write_bytes(pickle.dumps({"sessionid": "abc", "csrftoken": "t"}))
    r = invocar("conta-adicionar", "bot_coleta", "--sessao-arquivo", str(arq))
    assert r.exit_code == 0, r.output
    with fabrica() as s:
        conta = s.scalars(select(ContaColeta)).one()
        assert conta.usuario_ig == "bot_coleta"
        assert "abc" not in conta.sessao_criptografada
        assert decifrar_sessao(conta.sessao_criptografada, chave) == {
            "sessionid": "abc", "csrftoken": "t"}


def test_conta_adicionar_sem_chave_falha(fabrica, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "get_settings", lambda: SimpleNamespace(chave_sessao=""))
    arq = tmp_path / "sessao"
    arq.write_bytes(pickle.dumps({"sessionid": "abc"}))
    r = invocar("conta-adicionar", "bot", "--sessao-arquivo", str(arq))
    assert r.exit_code != 0


def criar_post(fabrica, extracao=None, status="erro"):
    with fabrica.begin() as s:
        p = Perfil(username="casa")
        s.add(p)
        s.flush()
        post = Post(perfil_id=p.id, shortcode="ABC", status=status, extracao=extracao,
                    erro_msg="falhou")
        s.add(post)
        s.flush()
        return post.id


def test_post_reprocessar_extracao_reenfileira_extrair(fabrica):
    pid = criar_post(fabrica, extracao={"eventos": []})
    r = invocar("post-reprocessar", "ABC")
    assert r.exit_code == 0, r.output
    with fabrica() as s:
        assert s.get(Post, pid).status == "pendente"
        job = s.scalars(select(Job)).one()
        assert (job.tipo, job.chave, job.payload) == (
            "extrair_post", f"extrair:{pid}", {"post_id": pid})


def test_post_reprocessar_reconciliacao_nao_apaga_extracao(fabrica):
    extracao = {"eventos": []}
    pid = criar_post(fabrica, extracao=extracao)
    r = invocar("post-reprocessar", "ABC", "--etapa", "reconciliacao")
    assert r.exit_code == 0, r.output
    with fabrica() as s:
        post = s.get(Post, pid)
        assert post.extracao == extracao
        assert post.status == "extraido"
        assert post.erro_msg is None
        job = s.scalars(select(Job)).one()
        assert (job.tipo, job.chave) == ("reconciliar_post", f"reconciliar:{pid}")


def test_post_reprocessar_reconciliacao_exige_extracao(fabrica):
    pid = criar_post(fabrica, extracao=None)
    r = invocar("post-reprocessar", "ABC", "--etapa", "reconciliacao")
    assert r.exit_code != 0
    with fabrica() as s:
        assert s.get(Post, pid).status == "erro"
        assert s.scalars(select(Job)).all() == []


def test_post_reprocessar_revive_job_em_erro(fabrica):
    pid = criar_post(fabrica, extracao=None)
    with fabrica.begin() as s:
        enfileirar(s, "extrair_post", {"post_id": pid}, chave=f"extrair:{pid}")
        job = s.scalars(select(Job)).one()
        job.status, job.tentativas, job.erro_msg = "erro", 5, "boom"
        job.executar_em = datetime.now(UTC) + timedelta(hours=1)
    r = invocar("post-reprocessar", "ABC")
    assert r.exit_code == 0, r.output
    assert "reativado" in r.output
    with fabrica() as s:
        job = s.scalars(select(Job)).one()
        assert (job.status, job.tentativas, job.erro_msg) == ("pendente", 0, None)
        assert job.executar_em <= datetime.now(UTC)
        assert s.get(Post, pid).status == "pendente"


def test_post_reprocessar_job_pendente_diz_que_ja_havia(fabrica):
    criar_post(fabrica)
    assert invocar("post-reprocessar", "ABC").exit_code == 0
    r = invocar("post-reprocessar", "ABC")
    assert "já havia" in r.output


def test_coletar_revive_job_em_erro_e_conta_so_efetivos(fabrica):
    invocar("perfil-adicionar", "casa")
    invocar("perfil-adicionar", "bar")
    with fabrica.begin() as s:
        casa = s.scalars(select(Perfil).where(Perfil.username == "casa")).one()
        bar = s.scalars(select(Perfil).where(Perfil.username == "bar")).one()
        enfileirar(s, "coletar_perfil", {"perfil_id": casa.id}, chave=f"coletar:{casa.id}")
        enfileirar(s, "coletar_perfil", {"perfil_id": bar.id}, chave=f"coletar:{bar.id}")
        for j in s.scalars(select(Job)).all():
            if j.payload["perfil_id"] == casa.id:
                j.status, j.tentativas, j.erro_msg = "erro", 5, "boom"
                j.executar_em = datetime.now(UTC) + timedelta(hours=1)
            else:  # já vencido: nada a fazer
                j.executar_em = datetime.now(UTC) - timedelta(minutes=1)
    r = invocar("coletar")
    assert r.exit_code == 0, r.output
    assert "1 de 2" in r.output
    with fabrica() as s:
        jobs = {j.payload["perfil_id"]: j for j in s.scalars(select(Job)).all()}
        assert len(jobs) == 2
        j = jobs[casa.id]
        assert (j.status, j.tentativas, j.erro_msg) == ("pendente", 0, None)
        assert j.executar_em <= datetime.now(UTC)


def test_post_reprocessar_inexistente_e_etapa_invalida(fabrica):
    assert invocar("post-reprocessar", "NAO").exit_code != 0
    criar_post(fabrica)
    assert invocar("post-reprocessar", "ABC", "--etapa", "xyz").exit_code != 0


def sp(ano, mes, dia, h=0, m=0):
    from agenda.extracao.regras import FUSO

    return datetime(ano, mes, dia, h, m, tzinfo=FUSO)


def test_eventos_filtra_por_cidade_e_periodo(fabrica):
    with fabrica.begin() as s:
        p = Perfil(username="casa")
        s.add(p)
        s.flush()
        post = Post(perfil_id=p.id, shortcode="A")
        s.add(post)
        s.flush()
        e1 = Evento(titulo="Show Um", inicio=sp(2030, 5, 10, 21, 30), local_nome="Casa Azul",
                    cidade="São Paulo", categoria="show")
        e2 = Evento(titulo="Expo Dois", inicio=sp(2030, 5, 20), hora_definida=False,
                    cidade="Campinas", categoria="exposicao")
        # 23:30 de 31/05 em SP já é 01/06 em UTC: o filtro deve usar o fuso de SP.
        e3 = Evento(titulo="Festa Tres", inicio=sp(2030, 5, 31, 23, 30), cidade="são paulo",
                    categoria="festa")
        s.add_all([e1, e2, e3])
        s.flush()
        s.add(EventoFonte(evento_id=e1.id, post_id=post.id, decisao="novo"))

    r = invocar("eventos")
    assert r.exit_code == 0, r.output
    assert "Show Um" in r.output and "10/05 21:30" in r.output
    assert "20/05 --:--" in r.output
    assert "Casa Azul" in r.output

    r = invocar("eventos", "--cidade", "SÃO PAULO")
    assert "Show Um" in r.output and "Festa Tres" in r.output
    assert "Expo Dois" not in r.output

    r = invocar("eventos", "--de", "2030-05-15", "--ate", "2030-05-31")
    assert "Expo Dois" in r.output and "Festa Tres" in r.output
    assert "Show Um" not in r.output

    r = invocar("eventos", "--ate", "2030-05-10")
    assert "Show Um" in r.output and "Expo Dois" not in r.output

    assert invocar("eventos", "--de", "ontem").exit_code != 0
