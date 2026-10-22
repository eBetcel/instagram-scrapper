"""CLI de admin. Os comandos abrem sessões por `agenda.cli.fabrica_sessoes`, que os
testes apontam para o banco do testcontainer (com commit real e TRUNCATE depois)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker
from typer.testing import CliRunner

from agenda import cli
from agenda.jobs import enfileirar
from agenda.models import Evento, EventoFonte, Job, Perfil, Post

runner = CliRunner()
TABELAS = "convites, revisoes_evento, evento_fontes, eventos, posts, perfis, jobs"


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
        assert s.scalars(select(Perfil)).one().fixo


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
    assert "próxima coleta" not in r.output


def criar_post(fabrica, extracao=None, status="erro"):
    with fabrica.begin() as s:
        p = Perfil(fixo=True, username="casa")
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


def test_post_reprocessar_inexistente_e_etapa_invalida(fabrica):
    assert invocar("post-reprocessar", "NAO").exit_code != 0
    criar_post(fabrica)
    assert invocar("post-reprocessar", "ABC", "--etapa", "xyz").exit_code != 0


def sp(ano, mes, dia, h=0, m=0):
    from agenda.extracao.regras import FUSO

    return datetime(ano, mes, dia, h, m, tzinfo=FUSO)


def test_eventos_filtra_por_cidade_e_periodo(fabrica):
    with fabrica.begin() as s:
        p = Perfil(fixo=True, username="casa")
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


# --- build_deps ----------------------------------------------------------------


def test_build_deps_recusa_sem_openai_api_key(capsys):
    import typer

    from agenda.cli import build_deps
    from agenda.config import Settings

    settings = Settings(openai_api_key="", openai_modelo_extracao="x", openai_modelo_reconciliacao="y")
    with pytest.raises(typer.Exit):
        build_deps(settings)
    assert "OPENAI_API_KEY" in capsys.readouterr().err


def test_build_deps_recusa_sem_apify_token(capsys):
    import typer

    from agenda.cli import build_deps
    from agenda.config import Settings

    settings = Settings(
        openai_api_key="k", apify_token="",
        openai_modelo_extracao="x", openai_modelo_reconciliacao="y",
    )
    with pytest.raises(typer.Exit):
        build_deps(settings)
    assert "APIFY_TOKEN" in capsys.readouterr().err


def test_worker_padrao_so_extrai():
    assert cli.TIPOS_PADRAO == "extrair_post"


def _duplicatas(fabrica):
    from agenda.extracao.regras import FUSO
    dia = (datetime.now(UTC) + timedelta(days=10)).astimezone(FUSO).replace(hour=0, minute=0, second=0, microsecond=0)
    with fabrica() as s:
        s.add_all([
            Evento(titulo="Festival Dosol 2026", inicio=dia, hora_definida=False, categoria="festival"),
            Evento(titulo="Festival Dosol 2026 na Sede", inicio=dia, hora_definida=False, categoria="festival"),
        ])
        s.commit()


def _n_eventos(fabrica):
    with fabrica() as s:
        return len(list(s.scalars(select(Evento))))


def test_deduplicar_sem_aplicar_so_lista(fabrica):
    _duplicatas(fabrica)
    r = invocar("deduplicar")
    assert r.exit_code == 0, r.output
    assert "Festival Dosol 2026" in r.output and "simulação" in r.output
    assert _n_eventos(fabrica) == 2


def test_deduplicar_com_aplicar_funde(fabrica):
    _duplicatas(fabrica)
    r = invocar("deduplicar", "--aplicar")
    assert r.exit_code == 0, r.output
    assert "1 fusão" in r.output
    assert _n_eventos(fabrica) == 1


def test_perfil_adicionar_marca_fixo(fabrica):
    assert invocar("perfil-adicionar", "casa_fixa").exit_code == 0
    with fabrica() as s:
        assert s.scalar(select(Perfil.fixo).where(Perfil.username == "casa_fixa")) is True


def test_convite_criar_e_listar(fabrica):
    import re

    from agenda.models import Convite

    r = invocar("convite-criar", "--usos", "3", "--dias", "7")
    assert r.exit_code == 0, r.output
    assert re.search(r"[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}", r.output)
    with fabrica() as s:
        c = s.scalars(select(Convite)).one()
        assert c.usos_restantes == 3 and c.expira_em is not None
    r = invocar("convite-listar")
    assert r.exit_code == 0 and "3" in r.output
