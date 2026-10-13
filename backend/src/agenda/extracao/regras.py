from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from agenda.extracao.schema import EventoExtraido

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
