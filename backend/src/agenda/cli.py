"""CLI de admin (`agenda ...`).

Os comandos abrem sessões por `fabrica_sessoes()` (os testes a substituem). Só os
comandos de worker chamam `build_deps`, então os demais funcionam sem chave da OpenAI.
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated

import typer
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from agenda.config import Settings, get_settings, parse_horarios
from agenda import texto
from agenda.db import get_session_factory, session_scope
from agenda.extracao.regras import FUSO
from agenda.jobs import reativar_ou_enfileirar
from agenda.models import Evento, EventoFonte, LoteColeta, Perfil, Post
from agenda.pipeline import Dependencias

app = typer.Typer(help="Administração do núcleo de dados da agenda cultural.", no_args_is_help=True)

# Instagram: letras, dígitos, '.' e '_' (até 30 caracteres).
TIPOS_PADRAO = "coletar_lote,extrair_post"


def fabrica_sessoes() -> sessionmaker[Session]:
    return get_session_factory()


def _sessao():
    return session_scope(fabrica_sessoes())


def _falhar(msg: str) -> typer.Exit:
    typer.echo(msg, err=True)
    return typer.Exit(1)


def normalizar_username(bruto: str) -> str:
    username = texto.normalizar_username(bruto)
    if username is None:
        raise _falhar(
            f"Username inválido: {bruto!r} (use letras, dígitos, '.' e '_', até 30 caracteres)."
        )
    return username


def build_deps(settings: Settings) -> Dependencias:
    """Monta as dependências reais do pipeline a partir das Settings."""
    from openai import OpenAI

    from agenda.coleta.apify import ApifyCliente, ApifyColetor
    from agenda.extracao.extrator import OpenAIExtrator
    from agenda.reconciliacao.decisao import OpenAIReconciliador
    from agenda.storage import S3Storage

    if not settings.openai_api_key.get_secret_value():
        raise _falhar("OPENAI_API_KEY não configurada.")
    if not settings.apify_token.get_secret_value():
        raise _falhar("APIFY_TOKEN não configurado.")
    client = OpenAI(api_key=settings.openai_api_key.get_secret_value())
    return Dependencias(
        storage=S3Storage.from_settings(settings),
        extrator=OpenAIExtrator(client, settings.openai_modelo_extracao),
        reconciliador=OpenAIReconciliador(client, settings.openai_modelo_reconciliacao),
        coletor=ApifyColetor(ApifyCliente(settings.apify_token.get_secret_value(), settings.apify_actor_id)),
        preco_por_post=settings.apify_preco_por_post,
        horarios_coleta=parse_horarios(settings.horarios_coleta),
    )


@app.command("perfil-adicionar")
def perfil_adicionar(username: str) -> None:
    """Cadastra um perfil do Instagram para coleta (idempotente)."""
    username = normalizar_username(username)
    with _sessao() as s:
        if s.scalar(select(Perfil.id).where(Perfil.username == username)) is not None:
            typer.echo(f"Perfil @{username} já existe.")
            return
        s.add(Perfil(username=username, fixo=True))
    typer.echo(f"Perfil @{username} adicionado.")


@app.command("perfil-listar")
def perfil_listar() -> None:
    """Lista os perfis cadastrados."""
    with _sessao() as s:
        perfis = s.scalars(select(Perfil).order_by(Perfil.username)).all()
        linhas = [(p.username, p.status, _fmt_dt(p.ultima_coleta_em)) for p in perfis]
    _tabela(["perfil", "status", "última coleta"], linhas)


@app.command("coletar")
def coletar(
    perfil: Annotated[str | None, typer.Option("--perfil", help="Só este perfil (sem: todos os acompanhados).")] = None,
) -> None:
    """Cria já um lote de coleta e enfileira (o worker o executa).

    Perfis que já estão num lote pendente ou em execução são pulados."""
    from agenda.coleta.servico import criar_lotes_imediatos, perfis_acompanhados

    agora = datetime.now(UTC)
    with _sessao() as s:
        if perfil is not None:
            username = normalizar_username(perfil)
            linha = s.execute(
                select(Perfil.username, Perfil.ultima_coleta_em).where(Perfil.username == username)
            ).one_or_none()
            if linha is None:
                raise _falhar(f"Perfil @{username} não cadastrado (use `agenda perfil-adicionar`).")
            alvos = [(linha[0], linha[1])]
        else:
            alvos = perfis_acompanhados(s)
        if not alvos:
            raise _falhar("Nenhum perfil acompanhado para coletar.")
        em_lote = set(
            s.scalars(
                select(func.unnest(LoteColeta.perfis)).where(
                    LoteColeta.status.in_(("pendente", "executando"))
                )
            )
        )
        pulados = [u for u, _ in alvos if u in em_lote]
        alvos = [(u, ultima) for u, ultima in alvos if u not in em_lote]
        lotes = criar_lotes_imediatos(s, agora, alvos) if alvos else []
        resumo = [(l.id, len(l.perfis), l.janela) for l in lotes]
    if pulados:
        typer.echo(
            "Já em lote pendente ou em execução (pulados): "
            + ", ".join(f"@{u}" for u in pulados)
        )
    if not resumo:
        typer.echo("Nenhum lote criado.")
    for lote_id, n, janela in resumo:
        typer.echo(f"Lote {lote_id} criado: {n} perfil(is), janela {janela}.")


@app.command("lotes")
def lotes(
    ultimos: Annotated[int, typer.Option("--ultimos", min=1, help="Quantos lotes mostrar.")] = 10,
) -> None:
    """Lista os últimos lotes de coleta e o custo estimado do mês (fuso de São Paulo)."""
    inicio_mes = datetime.now(FUSO).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    with _sessao() as s:
        linhas = [
            (
                str(l.id), l.tipo, _fmt_dt(l.criado_em), l.status, str(len(l.perfis)),
                str(l.posts), str(l.posts_novos), f"{l.custo_estimado:.4f}",
            )
            for l in s.scalars(select(LoteColeta).order_by(LoteColeta.id.desc()).limit(ultimos))
        ]
        total = s.scalar(
            select(func.coalesce(func.sum(LoteColeta.custo_estimado), 0)).where(
                LoteColeta.criado_em >= inicio_mes
            )
        )
    _tabela(["id", "tipo", "criado", "status", "perfis", "posts", "novos", "custo"], linhas)
    typer.echo(f"Total do mês (custo estimado): US$ {total:.4f}")


@app.command("convite-criar")
def convite_criar(
    usos: Annotated[int, typer.Option("--usos", min=1, help="Quantas contas o código cria.")] = 1,
    dias: Annotated[int | None, typer.Option("--dias", min=1, help="Validade em dias (sem: não expira).")] = None,
) -> None:
    """Cria um código de convite para o piloto (mostrado só agora)."""
    from agenda.api.seguranca import criar_convite

    with _sessao() as s:
        codigo = criar_convite(s, usos=usos, dias=dias, agora=datetime.now(UTC))
    validade = f"por {dias} dia(s)" if dias else "sem validade"
    typer.echo(f"Convite {codigo} — {usos} uso(s), {validade}.")


@app.command("convite-listar")
def convite_listar() -> None:
    """Lista os convites (o código não é guardado: só o começo do hash)."""
    from agenda.models import Convite

    with _sessao() as s:
        linhas = [
            (c.codigo_hash[:8], str(c.usos_restantes), _fmt_dt(c.expira_em), _fmt_dt(c.criado_em))
            for c in s.scalars(select(Convite).order_by(Convite.id))
        ]
    _tabela(["hash", "usos restantes", "expira em", "criado em"], linhas)


@app.command("api")
def api(
    porta: Annotated[int, typer.Option("--porta", help="Porta HTTP.")] = 8000,
    recarregar: Annotated[bool, typer.Option("--recarregar", help="Recarrega ao mudar o código.")] = False,
) -> None:
    """Sobe a api do produto web (rotas em /api)."""
    import uvicorn

    uvicorn.run("agenda.api.app:app_real", factory=True, host="0.0.0.0", port=porta, reload=recarregar)


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
