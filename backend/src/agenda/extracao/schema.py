from datetime import date, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

Categoria = Literal[
    "show", "festa", "exposicao", "teatro", "cinema", "oficina", "festival", "outro"
]
StatusIndicado = Literal["adiado", "cancelado", "esgotado"]


class Confianca(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_inicio: float
    hora_inicio: float
    local_nome: float


class EventoExtraido(BaseModel):
    """Compativel com structured outputs estritos da OpenAI (R18): todos os
    campos obrigatorios (anulaveis via `X | None`), sem defaults."""

    model_config = ConfigDict(extra="forbid")

    titulo: str | None
    descricao: str | None
    data_inicio: date | None
    hora_inicio: time | None
    data_fim: date | None
    hora_fim: time | None
    local_nome: str | None
    endereco: str | None
    cidade: str | None
    categoria: Categoria
    preco_texto: str | None
    gratuito: bool | None
    preco_min: float | None
    preco_max: float | None
    link_ingresso: str | None
    artistas: list[str]
    status_indicado: StatusIndicado | None
    confianca: Confianca

    @field_validator("hora_inicio", "hora_fim")
    @classmethod
    def _hora_local(cls, v: time | None) -> time | None:
        # Horas de flyer são sempre locais; o modelo às vezes anexa "Z" ou "-03:00".
        return v.replace(tzinfo=None) if v is not None else None


class ExtracaoPost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eventos: list[EventoExtraido]
