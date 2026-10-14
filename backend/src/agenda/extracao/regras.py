from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from agenda.extracao.schema import Confianca, EventoExtraido
from agenda.texto import normalizar

FUSO = ZoneInfo("America/Sao_Paulo")

_DIAS = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]


def filtrar_validos(eventos: list[EventoExtraido], agora: datetime) -> list[EventoExtraido]:
    hoje = agora.astimezone(FUSO).date()
    return [
        e
        for e in eventos
        if e.titulo
        and e.titulo.strip()
        and e.data_inicio is not None
        and (e.data_fim or e.data_inicio) >= hoje
    ]


def para_inicio(e: EventoExtraido) -> tuple[datetime, bool]:
    assert e.data_inicio is not None
    hora = e.hora_inicio or time(0, 0)
    return datetime.combine(e.data_inicio, hora, tzinfo=FUSO), e.hora_inicio is not None


def para_fim(e: EventoExtraido) -> datetime | None:
    if e.data_fim is None and e.hora_fim is None:
        return None
    if e.data_fim is not None:
        return datetime.combine(e.data_fim, e.hora_fim or time(23, 59), tzinfo=FUSO)
    assert e.data_inicio is not None and e.hora_fim is not None
    dia: date = e.data_inicio
    if e.hora_inicio is not None and e.hora_fim <= e.hora_inicio:
        dia += timedelta(days=1)
    return datetime.combine(dia, e.hora_fim, tzinfo=FUSO)


def normalizar_preco(e: EventoExtraido) -> EventoExtraido:
    if e.gratuito is True:
        return e.model_copy(update={"preco_min": 0.0, "preco_max": 0.0})
    if e.preco_min is not None and e.preco_max is not None and e.preco_min > e.preco_max:
        return e.model_copy(update={"preco_min": e.preco_max, "preco_max": e.preco_min})
    return e.model_copy()


def instrucoes_datas(publicado_em: datetime) -> str:
    d = publicado_em.astimezone(FUSO).date()
    return (
        f"O post foi publicado em {d.isoformat()} ({_DIAS[d.weekday()]}). "
        "Use essa data para resolver referências relativas como 'sexta que vem' "
        "ou 'amanhã'. Se o dia/mês já passou em relação à data do post, "
        "assuma o ano seguinte."
    )


def _comum(valores: list[str | None]) -> str | None:
    """O valor se todos os preenchidos coincidem (normalizados); senão, None."""
    preenchidos = [v for v in valores if v and v.strip()]
    if preenchidos and len({normalizar(v) for v in preenchidos}) == 1:
        return preenchidos[0]
    return None


def _primeiro(valores: list):
    return next((v for v in valores if v is not None), None)


def _linha_atracao(e: EventoExtraido) -> str:
    extras = [x for x in (e.local_nome, e.hora_inicio and e.hora_inicio.strftime("%H:%M")) if x]
    return f"- {e.titulo}" + (f" ({', '.join(extras)})" if extras else "")


def _status(grupo: list[EventoExtraido]):
    status = [e.status_indicado for e in grupo]
    if "esgotado" in status:
        return "esgotado"
    for s in ("cancelado", "adiado"):
        if all(x == s for x in status):
            return s
    return None


def _agrupar(grupo: list[EventoExtraido]) -> EventoExtraido:
    nome = grupo[0].festival
    artistas: dict[str, str] = {}
    for e in grupo:
        for a in e.artistas:
            artistas.setdefault(normalizar(a), a)
    horas = [e.hora_inicio for e in grupo if e.hora_inicio is not None]
    fins = [e.hora_fim for e in grupo if e.hora_fim is not None]
    minimos = [e.preco_min for e in grupo if e.preco_min is not None]
    maximos = [e.preco_max for e in grupo if e.preco_max is not None]
    gratuitos = [e.gratuito for e in grupo]
    return EventoExtraido(
        titulo=nome,
        descricao="\n".join(_linha_atracao(e) for e in grupo if e.titulo),
        data_inicio=grupo[0].data_inicio,
        hora_inicio=min(horas) if horas else None,
        data_fim=None,
        hora_fim=max(fins) if fins else None,
        local_nome=_comum([e.local_nome for e in grupo]),
        endereco=_comum([e.endereco for e in grupo]),
        cidade=_comum([e.cidade for e in grupo]),
        categoria="festival",
        preco_texto=_primeiro([e.preco_texto for e in grupo]),
        gratuito=True if all(g is True for g in gratuitos) else _primeiro([g for g in gratuitos if g is False]),
        preco_min=min(minimos) if minimos else None,
        preco_max=max(maximos) if maximos else None,
        link_ingresso=_primeiro([e.link_ingresso for e in grupo]),
        artistas=list(artistas.values()),
        festival=nome,
        status_indicado=_status(grupo),
        confianca=Confianca(
            data_inicio=min(e.confianca.data_inicio for e in grupo),
            hora_inicio=min(e.confianca.hora_inicio for e in grupo),
            local_nome=min(e.confianca.local_nome for e in grupo),
        ),
    )


def agrupar_festivais(eventos: list[EventoExtraido]) -> list[EventoExtraido]:
    """Atrações do mesmo festival no mesmo dia viram um único evento do festival,
    na posição do primeiro membro; eventos sem festival passam intactos."""
    grupos: dict[tuple[str, date | None], list[EventoExtraido]] = {}
    ordem: list[EventoExtraido | tuple[str, date | None]] = []
    for e in eventos:
        if not (e.festival and e.festival.strip()):
            ordem.append(e)
            continue
        chave = (normalizar(e.festival), e.data_inicio)
        if chave not in grupos:
            grupos[chave] = []
            ordem.append(chave)
        grupos[chave].append(e)
    return [_agrupar(grupos[x]) if isinstance(x, tuple) else x for x in ordem]
