"""Serviço de coleta.

Nenhuma função faz commit: a transação pertence a quem chama. A exceção é
`gravador_de_run_ids`, que grava o id de cada execução da Apify numa transação
própria, para sobreviver ao rollback do handler (R16).
"""

import logging
import math
import urllib.request
from collections.abc import Callable, Sequence
from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import exists, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from agenda.coleta.apify import classificar_erro
from agenda.coleta.base import Coletor, PostColetado, ResultadoLote
from agenda.config import HORARIOS_COLETA_PADRAO, parse_horarios
from agenda.db import session_scope
from agenda.extracao.regras import FUSO
from agenda.jobs import enfileirar
from agenda.models import GrupoPerfil, LoteColeta, Perfil, Post
from agenda.storage import Storage

log = logging.getLogger(__name__)

PERFIS_POR_EXECUCAO = 50
HORARIOS_PADRAO = parse_horarios(HORARIOS_COLETA_PADRAO)
LIMITE_AGENDADO = 20
LIMITE_NOVOS = 50
JANELA_NOVOS = "30 days"
# Lote de novos em erro, ou perfil que já esteve num lote de novos, só volta depois disso,
# contado a partir do fim do lote: coalesce(concluido_em, criado_em) (R11). `agendar_lotes`
# grava `criado_em = agora` e o worker grava `concluido_em` com o mesmo relógio (deps.relogio).
ESPERA_NOVOS = timedelta(hours=1)
# Chave fixa do pg_advisory_xact_lock que serializa `agendar_lotes` entre workers.
LOCK_AGENDAMENTO = 7_310_002
# Tentativas de um job `coletar_lote` (cada uma reaproveita as execuções já iniciadas, R16).
MAX_TENTATIVAS_LOTE = 3


def baixar_url(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def ultimo_horario(agora: datetime, horarios: Sequence[time]) -> datetime:
    """O horário configurado mais recente que já passou (<= agora), em America/Sao_Paulo."""
    local = agora.astimezone(FUSO)
    candidatos = [
        datetime.combine(dia, h, tzinfo=FUSO)
        for dia in (local.date(), local.date() - timedelta(days=1))
        for h in horarios
    ]
    return max(c for c in candidatos if c <= local)


def janela_agendada(ultimo_concluido: datetime | None, agora: datetime) -> str:
    """Horas desde o último lote agendado concluído + 1 h, para cima; sem anterior, 30 dias."""
    if ultimo_concluido is None:
        return JANELA_NOVOS
    horas = max(0, math.ceil((agora - ultimo_concluido) / timedelta(hours=1)))
    return f"{horas + 1} hours"


def perfis_acompanhados(s: Session) -> list[tuple[str, datetime | None]]:
    """(username, ultima_coleta_em) dos perfis `ativo` e (`fixo` ou em algum grupo)."""
    em_grupo = exists().where(GrupoPerfil.perfil_id == Perfil.id)
    return [
        (u, ultima)
        for u, ultima in s.execute(
            select(Perfil.username, Perfil.ultima_coleta_em)
            .where(Perfil.status == "ativo", or_(Perfil.fixo, em_grupo))
            .order_by(Perfil.username)
        ).all()
    ]


def criar_lotes_imediatos(
    s: Session, agora: datetime, perfis: Sequence[tuple[str, datetime | None]]
) -> list[LoteColeta]:
    """Lotes `novos` (sem horário) já enfileirados: um para os nunca coletados (30 dias,
    limite 50) e outro para os já coletados (janela agendada, limite 20)."""
    nunca = [u for u, ultima in perfis if ultima is None]
    coletados = [u for u, ultima in perfis if ultima is not None]
    lotes: list[LoteColeta] = []
    if nunca:
        lotes.append(LoteColeta(
            tipo="novos", janela=JANELA_NOVOS, limite=LIMITE_NOVOS, perfis=nunca, criado_em=agora
        ))
    if coletados:
        ultimo_concluido = s.scalar(
            select(func.max(LoteColeta.concluido_em)).where(
                LoteColeta.tipo == "agendado", LoteColeta.status == "concluido"
            )
        )
        lotes.append(LoteColeta(
            tipo="novos", janela=janela_agendada(ultimo_concluido, agora),
            limite=LIMITE_AGENDADO, perfis=coletados, criado_em=agora,
        ))
    s.add_all(lotes)
    s.flush()
    for lote in lotes:
        enfileirar(
            s, "coletar_lote", {"lote_id": lote.id}, chave=f"lote:{lote.id}", executar_em=agora,
            max_tentativas=MAX_TENTATIVAS_LOTE,
        )
    return lotes


def agendar_lotes(
    s: Session, agora: datetime, horarios: Sequence[time] = HORARIOS_PADRAO
) -> list[int]:
    """Cria o lote agendado do horário mais recente (se ainda não existe) e o lote de
    perfis nunca coletados; enfileira `coletar_lote` para cada um. Devolve os ids criados.

    Perfis acompanhados: `ativo` e (`fixo` ou em algum grupo). Serializado por advisory
    lock: dois workers na manutenção ao mesmo tempo não criam dois lotes de novos.
    """
    s.execute(select(func.pg_advisory_xact_lock(LOCK_AGENDAMENTO)))
    acompanhados = perfis_acompanhados(s)
    criados: list[int] = []

    coletados = [u for u, ultima in acompanhados if ultima is not None]
    if coletados and horarios:
        ultimo_concluido = s.scalar(
            select(func.max(LoteColeta.concluido_em)).where(
                LoteColeta.tipo == "agendado", LoteColeta.status == "concluido"
            )
        )
        lote_id = s.execute(
            insert(LoteColeta)
            .values(
                tipo="agendado",
                horario=ultimo_horario(agora, horarios),
                janela=janela_agendada(ultimo_concluido, agora),
                limite=LIMITE_AGENDADO,
                perfis=coletados,
                criado_em=agora,
            )
            .on_conflict_do_nothing(
                index_elements=["horario"], index_where=text("tipo = 'agendado'")
            )
            .returning(LoteColeta.id)
        ).scalar_one_or_none()
        if lote_id is not None:
            criados.append(lote_id)

    novos = [u for u, ultima in acompanhados if ultima is None]
    if novos and not _novos_bloqueado(s, agora):
        recentes = set(
            s.scalars(
                select(func.unnest(LoteColeta.perfis)).where(
                    LoteColeta.tipo == "novos", _fim_do_lote() > agora - ESPERA_NOVOS
                )
            )
        )
        novos = [u for u in novos if u not in recentes]
        if novos:
            lote = LoteColeta(
                tipo="novos", janela=JANELA_NOVOS, limite=LIMITE_NOVOS, perfis=novos,
                criado_em=agora,
            )
            s.add(lote)
            s.flush()
            criados.append(lote.id)

    for lote_id in criados:
        enfileirar(
            s, "coletar_lote", {"lote_id": lote_id}, chave=f"lote:{lote_id}",
            max_tentativas=MAX_TENTATIVAS_LOTE,
        )
    return criados


def _fim_do_lote():
    return func.coalesce(LoteColeta.concluido_em, LoteColeta.criado_em)


def _novos_bloqueado(s: Session, agora: datetime) -> bool:
    """Há lote de novos pendente/executando, ou que terminou em erro há menos de 1 h."""
    return s.scalar(
        select(
            exists().where(
                LoteColeta.tipo == "novos",
                or_(
                    LoteColeta.status.in_(("pendente", "executando")),
                    (LoteColeta.status == "erro") & (_fim_do_lote() > agora - ESPERA_NOVOS),
                ),
            )
        )
    )


def gravador_de_run_ids(
    factory: sessionmaker[Session] | None, lote_id: int
) -> Callable[[int, str], None]:
    """Callback `(bloco, run_id)` que grava `lote.run_ids[bloco] = run_id` numa
    transação própria, já confirmada ao voltar (sobrevive ao rollback do handler)."""

    def gravar(bloco: int, run_id: str) -> None:
        with session_scope(factory) as s:
            lote = s.get(LoteColeta, lote_id, with_for_update=True)
            if lote is None:
                return
            ids = list(lote.run_ids or [])
            ids.extend([""] * (bloco + 1 - len(ids)))
            ids[bloco] = run_id
            lote.run_ids = ids

    return gravar


def coletar_lote(
    s: Session,
    lote_id: int,
    coletor: Coletor,
    storage: Storage,
    *,
    agora: datetime,
    baixar: Callable[[str], bytes] = baixar_url,
    preco_por_post: Decimal,
    gravar_run_id: Callable[[int, str], None] | None = None,
) -> int:
    """Coleta e grava os posts do lote; devolve quantos posts novos foram salvos.

    Os perfis vão em blocos de 50 (pela ordem de `lote.perfis`); o bloco `i` usa a
    execução `lote.run_ids[i]` de uma tentativa anterior, se houver (R16). Cada
    execução nova é passada a `gravar_run_id(i, run_id)` logo depois de iniciada.

    Falhas propagam (o worker decide): a transação de quem chama é desfeita, o lote
    volta a ler `pendente` (só os `run_ids` gravados por `gravar_run_id` ficam) e o
    worker o marca `erro` quando o job termina sem retentativa (R12).
    """
    lote = s.get(LoteColeta, lote_id)
    if lote is None:
        raise ValueError(f"lote {lote_id} não existe")
    if lote.status == "concluido":
        return 0
    # O lote não é alterado antes de coletar: `gravar_run_id` atualiza a mesma linha
    # noutra conexão e esperaria por um lock desta transação.

    perfis = {
        p.username: p
        for p in s.scalars(select(Perfil).where(Perfil.username.in_(lote.perfis)))
    }
    for u in lote.perfis:
        if u not in perfis:
            log.warning("lote %s: perfil @%s não existe; ignorado", lote.id, u)
    usernames = [u for u in lote.perfis if u in perfis]

    anteriores = list(lote.run_ids or [])
    resultado = ResultadoLote()
    run_ids: list[str] = []
    for bloco, i in enumerate(range(0, len(lote.perfis), PERFIS_POR_EXECUCAO)):
        # Blocos pela ordem de `lote.perfis` (estável entre tentativas), sem os removidos.
        parte_perfis = [u for u in lote.perfis[i : i + PERFIS_POR_EXECUCAO] if u in perfis]
        anterior = anteriores[bloco] if bloco < len(anteriores) and anteriores[bloco] else None
        if not parte_perfis:
            run_ids.append(anterior or "")
            continue
        ao_iniciar = (lambda r, b=bloco: gravar_run_id(b, r)) if gravar_run_id else None
        parte = coletor.coletar(
            parte_perfis, janela=lote.janela, limite=lote.limite,
            run_id=anterior, ao_iniciar=ao_iniciar,
        )
        resultado.posts.extend(parte.posts)
        resultado.erros.update(parte.erros)
        run_ids.append(parte.run_ids[0] if parte.run_ids else anterior or "")
    resultado.run_ids = run_ids

    novos = 0
    vistos: set[str] = set()
    existentes = set(
        s.scalars(
            select(Post.shortcode).where(
                Post.shortcode.in_([p.shortcode for p in resultado.posts])
            )
        )
    )
    for p in resultado.posts:
        if p.shortcode in existentes or p.shortcode in vistos:
            continue
        vistos.add(p.shortcode)
        perfil = perfis.get(p.perfil)
        if perfil is None:
            log.warning("lote %s: post %s de perfil fora do lote (@%s)", lote.id, p.shortcode, p.perfil)
            continue
        if _salvar_post(s, perfil, p, storage, baixar):
            novos += 1

    for username, msg in resultado.erros.items():
        perfil = perfis.get(username)
        if perfil is None:
            continue
        if classificar_erro(msg) == "inexistente":
            perfil.status = "inexistente"
        else:
            log.warning("lote %s: erro ao coletar @%s: %s", lote.id, username, msg)
    for username in usernames:
        if username not in resultado.erros:
            perfis[username].ultima_coleta_em = agora

    lote.posts = len(resultado.posts)
    lote.posts_novos = novos
    lote.custo_estimado = (Decimal(lote.posts) * preco_por_post).quantize(Decimal("0.0001"))
    lote.run_ids = resultado.run_ids
    lote.status = "concluido"
    lote.concluido_em = agora
    s.flush()
    return novos


def _salvar_post(s: Session, perfil: Perfil, p: PostColetado, storage: Storage, baixar) -> bool:
    dados: list[bytes] = []
    for url in p.urls_imagens:
        try:
            dados.append(baixar(url))
        except Exception as e:
            log.warning("post %s: imagem não baixada (%s): %s", p.shortcode, url, e)
    chaves = [f"posts/{p.shortcode}/{n}.jpg" for n in range(len(dados))]
    post_id = s.execute(
        insert(Post)
        .values(
            perfil_id=perfil.id,
            shortcode=p.shortcode,
            legenda=p.legenda,
            publicado_em=p.publicado_em,
            imagens=chaves,
            status="pendente",
        )
        .on_conflict_do_nothing(index_elements=["shortcode"])
        .returning(Post.id)
    ).scalar_one_or_none()
    if post_id is None:
        return False
    for chave, d in zip(chaves, dados):
        storage.salvar(chave, d, "image/jpeg")
    enfileirar(s, "extrair_post", {"post_id": post_id}, chave=f"extrair:{post_id}")
    return True
