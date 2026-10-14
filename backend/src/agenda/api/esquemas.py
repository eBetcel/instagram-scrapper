"""Formatos de saída da api."""

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
    eventos: list[dict]
    sou_dono: bool
    sigo: bool
