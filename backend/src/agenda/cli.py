"""CLI de admin (`agenda ...`).

Os comandos abrem sessões por `fabrica_sessoes()` (os testes a substituem). Só os
comandos de worker chamam `build_deps`, então os demais funcionam sem chave da OpenAI.
"""

import pickle
import re
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from agenda.config import Settings, get_settings
from agenda.db import get_session_factory, session_scope
from agenda.extracao.regras import FUSO
from agenda.jobs import reativar_ou_enfileirar
from agenda.models import ContaColeta, Evento, EventoFonte, Job, Perfil, Post
from agenda.pipeline import Dependencias

app = typer.Typer(help="Administração do núcleo de dados da agenda cultural.", no_args_is_help=True)

# Instagram: letras, dígitos, '.' e '_' (até 30 caracteres).
_USERNAME_RE = re.compile(r"^[a-z0-9._]{1,30}$")
TIPOS_PADRAO = "coletar_perfil,extrair_post"


def fabrica_sessoes() -> sessionmaker[Session]:
    return get_session_factory()


def _sessao():
    return session_scope(fabrica_sessoes())


def _falhar(msg: str) -> typer.Exit:
    typer.echo(msg, err=True)
    return typer.Exit(1)


def normalizar_username(bruto: str) -> str:
    username = bruto.strip().removeprefix("@").lower()
    if not _USERNAME_RE.match(username):
        raise _falhar(
            f"Username inválido: {bruto!r} (use letras, dígitos, '.' e '_', até 30 caracteres)."
        )
    return username


def _validar_chave_sessao(chave: str) -> None:
    """Falha já na partida se CHAVE_SESSAO não for uma chave Fernet (e não na 1ª coleta)."""
    from cryptography.fernet import Fernet

    if not chave:
        raise _falhar("CHAVE_SESSAO não configurada (chave Fernet; veja .env.example).")
    try:
        Fernet(chave.encode())
    except ValueError as exc:
        raise _falhar(f"CHAVE_SESSAO inválida (esperada uma chave Fernet): {exc}") from exc


def build_deps(settings: Settings) -> Dependencias:
    """Monta as dependências reais do pipeline a partir das Settings."""
    from openai import OpenAI

    from agenda.coleta.instaloader_coletor import InstaloaderColetor
    from agenda.coleta.pool import PoolContas
    from agenda.extracao.extrator import OpenAIExtrator
    from agenda.reconciliacao.decisao import OpenAIReconciliador
    from agenda.storage import S3Storage

    if not settings.openai_api_key:
        raise _falhar("OPENAI_API_KEY não configurada.")
    _validar_chave_sessao(settings.chave_sessao)
    client = OpenAI(api_key=settings.openai_api_key)
    pool = PoolContas(get_session_factory(), settings.limite_requisicoes_conta_hora)
    return Dependencias(
        coletor=InstaloaderColetor(pool),
        storage=S3Storage.from_settings(settings),
        extrator=OpenAIExtrator(client, settings.openai_modelo_extracao),
        reconciliador=OpenAIReconciliador(client, settings.openai_modelo_reconciliacao),
        intervalo_coleta_horas=settings.intervalo_coleta_horas,
    )


@app.command("perfil-adicionar")
def perfil_adicionar(username: str) -> None:
    """Cadastra um perfil do Instagram para coleta (idempotente)."""
    username = normalizar_username(username)
    with _sessao() as s:
        if s.scalar(select(Perfil.id).where(Perfil.username == username)) is not None:
            typer.echo(f"Perfil @{username} já existe.")
            return
        s.add(Perfil(username=username, proxima_coleta_em=func.now()))
    typer.echo(f"Perfil @{username} adicionado.")


@app.command("perfil-listar")
def perfil_listar() -> None:
    """Lista os perfis cadastrados."""
    with _sessao() as s:
        perfis = s.scalars(select(Perfil).order_by(Perfil.username)).all()
        linhas = [
            (p.username, p.status, _fmt_dt(p.ultima_coleta_em), _fmt_dt(p.proxima_coleta_em))
            for p in perfis
        ]
    _tabela(["perfil", "status", "última coleta", "próxima coleta"], linhas)


@app.command("conta-adicionar")
def conta_adicionar(
    usuario_ig: str,
    sessao_arquivo: Annotated[Path, typer.Option("--sessao-arquivo", help="Arquivo de sessão do instaloader.")],
) -> None:
    """Cadastra uma conta de coleta com a sessão criptografada.

    O arquivo é o gerado por `instaloader --login X` / `save_session_to_file`: um
    pickle do dict de cookies. É lido com `pickle.load` diretamente (é o que o próprio
    instaloader faz); use apenas arquivos que você mesmo gerou.
    """
    from agenda.coleta.pool import cifrar_sessao

    chave = get_settings().chave_sessao
    if not chave:
        raise _falhar("CHAVE_SESSAO não configurada (chave Fernet; veja .env.example).")
    try:
        with open(sessao_arquivo, "rb") as f:
            cookies = pickle.load(f)  # noqa: S301 - arquivo local do próprio admin
    except Exception as exc:  # noqa: BLE001
        raise _falhar(f"Não foi possível ler {sessao_arquivo}: {exc}") from exc
    if not isinstance(cookies, dict) or not cookies:
        raise _falhar("Arquivo de sessão inválido: esperado um dict de cookies não vazio.")
    usuario_ig = usuario_ig.strip().removeprefix("@")
    token = cifrar_sessao(cookies, chave)
    with _sessao() as s:
        conta = s.scalars(select(ContaColeta).where(ContaColeta.usuario_ig == usuario_ig)).one_or_none()
        if conta is None:
            s.add(ContaColeta(usuario_ig=usuario_ig, sessao_criptografada=token))
            typer.echo(f"Conta {usuario_ig} adicionada.")
        else:
            conta.sessao_criptografada = token
            conta.status = "ativa"
            conta.bloqueada_ate = None
            typer.echo(f"Conta {usuario_ig} já existia: sessão atualizada e conta reativada.")


@app.command("coletar")
def coletar(
    perfil: Annotated[str | None, typer.Option(help="Username; sem ele, todos os perfis ativos.")] = None,
) -> None:
    """Enfileira a coleta imediatamente."""
    with _sessao() as s:
        consulta = select(Perfil).where(Perfil.status == "ativo").order_by(Perfil.id)
        if perfil is not None:
            consulta = select(Perfil).where(Perfil.username == normalizar_username(perfil))
        perfis = s.scalars(consulta).all()
        if not perfis:
            raise _falhar("Nenhum perfil encontrado.")
        agora = datetime.now(UTC)
        efetivos = 0
        for p in perfis:
            p.proxima_coleta_em = agora
            chave = f"coletar:{p.id}"
            r = reativar_ou_enfileirar(s, "coletar_perfil", {"perfil_id": p.id}, chave, executar_em=agora)
            if r == "existente":  # job vivo: adianta se estiver pendente e ainda não vencido
                pendente = s.scalars(
                    select(Job).where(
                        Job.tipo == "coletar_perfil", Job.chave == chave, Job.status == "pendente",
                        Job.executar_em > agora,
                    )
                ).one_or_none()
                if pendente is not None:
                    pendente.executar_em = agora
                    efetivos += 1
            else:
                efetivos += 1
    typer.echo(f"Coleta enfileirada ou adiantada para {efetivos} de {len(perfis)} perfil(is).")


@app.command("worker")
def worker(
    tipos: Annotated[str, typer.Option(help="Tipos de job, separados por vírgula.")] = TIPOS_PADRAO,
    uma_vez: Annotated[bool, typer.Option("--uma-vez", help="Sai quando não houver job pronto.")] = False,
) -> None:
    """Roda o worker de coleta e extração."""
    _rodar(
        [t.strip() for t in tipos.split(",") if t.strip()],
        uma_vez,
    )


@app.command("worker-reconciliacao")
def worker_reconciliacao(
    uma_vez: Annotated[bool, typer.Option("--uma-vez", help="Sai quando não houver job pronto.")] = False,
) -> None:
    """Roda o worker de reconciliação (um único processo; é serial)."""
    _rodar(["reconciliar_post"], uma_vez)


def _rodar(tipos: list[str], uma_vez: bool) -> None:
    import logging

    from agenda.pipeline import HANDLERS
    from agenda.worker import rodar_worker

    desconhecidos = [t for t in tipos if t not in HANDLERS]
    if not tipos or desconhecidos:
        raise _falhar(f"Tipos inválidos: {desconhecidos or tipos}. Válidos: {', '.join(HANDLERS)}.")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    deps = build_deps(get_settings())
    n = rodar_worker(deps, tipos, session_factory=fabrica_sessoes(), uma_vez=uma_vez)
    typer.echo(f"{n} job(s) processado(s).")


@app.command("post-reprocessar")
def post_reprocessar(
    shortcode: str,
    etapa: Annotated[str, typer.Option(help="extracao ou reconciliacao.")] = "extracao",
) -> None:
    """Reenfileira só a etapa pedida de um post (a reconciliação reaproveita a extração)."""
    if etapa not in ("extracao", "reconciliacao"):
        raise _falhar(f"Etapa inválida: {etapa!r} (use extracao ou reconciliacao).")
    with _sessao() as s:
        post = s.scalars(select(Post).where(Post.shortcode == shortcode)).one_or_none()
        if post is None:
            raise _falhar(f"Post {shortcode} não encontrado.")
        if etapa == "extracao":
            post.status = "pendente"
            tipo, chave = "extrair_post", f"extrair:{post.id}"
        else:
            if post.extracao is None:
                raise _falhar(f"Post {shortcode} não tem extração; use --etapa extracao.")
            post.status = "extraido"
            tipo, chave = "reconciliar_post", f"reconciliar:{post.id}"
        post.erro_msg = None
        s.flush()
        r = reativar_ou_enfileirar(s, tipo, {"post_id": post.id}, chave)
    typer.echo({
        "novo": f"Post {shortcode}: {tipo} enfileirado.",
        "reativado": f"Post {shortcode}: {tipo} com erro reativado.",
        "existente": f"Post {shortcode}: já havia {tipo} pendente ou em execução.",
    }[r])


def _data(valor: str | None, opcao: str) -> date | None:
    if valor is None:
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise _falhar(f"{opcao}: data inválida {valor!r} (use YYYY-MM-DD).") from None


@app.command("eventos")
def eventos(
    cidade: Annotated[str | None, typer.Option(help="Filtra pela cidade (sem distinguir maiúsculas).")] = None,
    de: Annotated[str | None, typer.Option("--de", help="Início a partir de YYYY-MM-DD.")] = None,
    ate: Annotated[str | None, typer.Option("--ate", help="Início até YYYY-MM-DD (inclusive).")] = None,
) -> None:
    """Lista eventos (datas no fuso de São Paulo)."""
    d_de, d_ate = _data(de, "--de"), _data(ate, "--ate")
    fontes = (
        select(func.count()).select_from(EventoFonte).where(EventoFonte.evento_id == Evento.id)
        .scalar_subquery()
    )
    consulta = select(Evento, fontes).order_by(Evento.inicio, Evento.id)
    if cidade:
        consulta = consulta.where(func.lower(Evento.cidade) == cidade.strip().lower())
    if d_de:
        consulta = consulta.where(Evento.inicio >= datetime.combine(d_de, time.min, FUSO))
    if d_ate:
        consulta = consulta.where(
            Evento.inicio < datetime.combine(d_ate + timedelta(days=1), time.min, FUSO)
        )
    with _sessao() as s:
        linhas = [
            (e.titulo, _fmt_inicio(e), e.local_nome or "", e.cidade or "", e.status, str(n))
            for e, n in s.execute(consulta).all()
        ]
    _tabela(["título", "início", "local", "cidade", "status", "fontes"], linhas)


@app.command("deduplicar")
def deduplicar_cmd(
    aplicar: Annotated[bool, typer.Option("--aplicar", help="Funde de verdade (sem ele, só simula).")] = False,
) -> None:
    """Funde eventos duplicados (mesmo dia e nome parecido); sem --aplicar, só lista."""
    from agenda.reconciliacao.fusao import deduplicar

    s = fabrica_sessoes()()
    try:
        titulos = {e.id: (e.titulo, _fmt_inicio(e)) for e in s.scalars(select(Evento))}
        fusoes = deduplicar(s, agora=datetime.now(FUSO))
        for manter, removido in fusoes:
            titulo, quando = titulos[removido]
            typer.echo(f"{manter} <- {removido}  {titulo} ({quando})")
        if aplicar:
            s.commit()
            typer.echo(f"{len(fusoes)} fusão(ões) aplicada(s).")
        else:
            s.rollback()
            typer.echo(f"{len(fusoes)} fusão(ões) na simulação; use --aplicar para gravar.")
    finally:
        s.close()


def _fmt_inicio(e: Evento) -> str:
    local = e.inicio.astimezone(FUSO)
    return local.strftime("%d/%m %H:%M") if e.hora_definida else local.strftime("%d/%m --:--")


def _fmt_dt(dt: datetime | None) -> str:
    return dt.astimezone(FUSO).strftime("%d/%m/%Y %H:%M") if dt else "-"


def _tabela(cabecalho: list[str], linhas: list[tuple[str, ...]]) -> None:
    if not linhas:
        typer.echo("(nenhum resultado)")
        return
    larguras = [max(len(str(x)) for x in col) for col in zip(cabecalho, *linhas, strict=True)]
    for linha in [cabecalho, *linhas]:
        typer.echo("  ".join(str(c).ljust(w) for c, w in zip(linha, larguras, strict=True)).rstrip())


from agenda.avaliacao.cli import avaliar  # noqa: E402

app.command("avaliar")(avaliar)

if __name__ == "__main__":
    app()
