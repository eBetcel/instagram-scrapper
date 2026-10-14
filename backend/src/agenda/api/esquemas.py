"""Formatos de saída da api."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

StatusPerfil = Literal["ativo", "coletando", "privado", "inexistente"]


class PerfilNoGrupo(BaseModel):
    username: str
    status: StatusPerfil


class GrupoSaida(BaseModel):
    slug: str
    nome: str
    descricao: str | None
    curador: str
    n_perfis: int
    n_seguidores: int


class GrupoDetalhe(GrupoSaida):
    perfis: list[PerfilNoGrupo]
    eventos: list["EventoResumo"]
    sou_dono: bool
    sigo: bool


class EventoResumo(BaseModel):
    id: int
    titulo: str
    inicio: datetime
    hora_definida: bool
    fim: datetime | None
    local_nome: str | None
    cidade: str | None
    categoria: str
    preco_texto: str | None
    gratuito: bool | None
    preco_min: Decimal | None
    preco_max: Decimal | None
    link_ingresso: str | None
    status: str
    festival: str | None
    artistas: list[str]
    alterado: bool
    imagem: str | None


class FonteSaida(BaseModel):
    username: str
    shortcode: str
    url_instagram: str
    publicado_em: datetime | None
    decisao: str


class RevisaoSaida(BaseModel):
    campo: str
    valor_anterior: str | None
    valor_novo: str | None
    motivo: str | None
    criado_em: datetime


class EventoDetalhe(EventoResumo):
    descricao: str | None
    endereco: str | None
    fontes: list[FonteSaida]
    revisoes: list[RevisaoSaida]


GrupoDetalhe.model_rebuild()
