"""Grupos (curadorias de @s) e seguidores."""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from agenda.api.deps import deps_api, sessao_db, usuario_atual, usuario_opcional
from agenda.api.esquemas import GrupoDetalhe, GrupoSaida, PerfilNoGrupo
from agenda.models import Grupo, GrupoPerfil, GrupoSeguidor, Perfil, Usuario
from agenda.texto import slugificar

rotas = APIRouter(prefix="/api")


class GrupoEntrada(BaseModel):
    nome: str = Field(max_length=80)
    descricao: str | None = Field(default=None, max_length=500)


class GrupoEdicao(BaseModel):
    nome: str | None = Field(default=None, max_length=80)
    descricao: str | None = Field(default=None, max_length=500)


def _nome(bruto: str) -> str:
    nome = bruto.strip()
    if not nome:
        raise HTTPException(422, "Dê um nome ao grupo")
    return nome


def slug_livre(s: Session, base: str) -> str:
    usados = set(s.scalars(select(Grupo.slug).where(
        (Grupo.slug == base) | Grupo.slug.like(f"{base}-%")
    )))
    if base not in usados:
        return base
    n = 2
    while f"{base}-{n}" in usados:
        n += 1
    return f"{base}-{n}"


def grupo_ou_404(s: Session, slug: str) -> Grupo:
    g = s.scalar(select(Grupo).where(Grupo.slug == slug))
    if g is None:
        raise HTTPException(404, "Grupo não encontrado")
    return g


def grupo_do_dono(s: Session, slug: str, u: Usuario) -> Grupo:
    g = grupo_ou_404(s, slug)
    if g.dono_id != u.id:
        raise HTTPException(403, "Só quem criou o grupo pode mudá-lo")
    return g


def _saidas(s: Session, grupos: list[Grupo]) -> list[GrupoSaida]:
    ids = [g.id for g in grupos]
    n_perfis = dict(s.execute(
        select(GrupoPerfil.grupo_id, func.count()).where(GrupoPerfil.grupo_id.in_(ids))
        .group_by(GrupoPerfil.grupo_id)
    ).all())
    n_seg = dict(s.execute(
        select(GrupoSeguidor.grupo_id, func.count()).where(GrupoSeguidor.grupo_id.in_(ids))
        .group_by(GrupoSeguidor.grupo_id)
    ).all())
    return [
        GrupoSaida(slug=g.slug, nome=g.nome, descricao=g.descricao, curador=g.dono.nome,
                   n_perfis=n_perfis.get(g.id, 0), n_seguidores=n_seg.get(g.id, 0))
        for g in grupos
    ]


def status_perfil(p: Perfil) -> str:
    if p.status in ("privado", "inexistente"):
        return p.status
    return "coletando" if p.ultima_coleta_em is None else "ativo"


@rotas.get("/grupos")
def listar(s: Session = Depends(sessao_db), u: Usuario = Depends(usuario_atual)) -> dict:
    meus = list(s.scalars(select(Grupo).where(Grupo.dono_id == u.id).order_by(Grupo.nome)))
    seguidos = list(s.scalars(
        select(Grupo).join(GrupoSeguidor, GrupoSeguidor.grupo_id == Grupo.id)
        .where(GrupoSeguidor.usuario_id == u.id).order_by(Grupo.nome)
    ))
    return {"meus": _saidas(s, meus), "seguidos": _saidas(s, seguidos)}


@rotas.post("/grupos", status_code=201)
def criar(dados: GrupoEntrada, s: Session = Depends(sessao_db), u: Usuario = Depends(usuario_atual),
          deps=Depends(deps_api)) -> GrupoSaida:
    limite = deps.config.limite_grupos_por_usuario
    if s.scalar(select(func.count()).select_from(Grupo).where(Grupo.dono_id == u.id)) >= limite:
        raise HTTPException(422, f"No piloto, cada pessoa pode ter até {limite} grupos")
    nome = _nome(dados.nome)
    g = Grupo(dono_id=u.id, nome=nome, descricao=dados.descricao, slug=slug_livre(s, slugificar(nome)))
    s.add(g)
    s.flush()
    return _saidas(s, [g])[0]


@rotas.get("/grupos/{slug}")
def detalhe(slug: str, s: Session = Depends(sessao_db),
            u: Usuario | None = Depends(usuario_opcional)) -> GrupoDetalhe:
    g = grupo_ou_404(s, slug)
    perfis = s.scalars(
        select(Perfil).join(GrupoPerfil, GrupoPerfil.perfil_id == Perfil.id)
        .where(GrupoPerfil.grupo_id == g.id).order_by(Perfil.username)
    )
    sigo = u is not None and s.get(GrupoSeguidor, (g.id, u.id)) is not None
    return GrupoDetalhe(
        **_saidas(s, [g])[0].model_dump(),
        perfis=[PerfilNoGrupo(username=p.username, status=status_perfil(p)) for p in perfis],
        eventos=[], sou_dono=u is not None and u.id == g.dono_id, sigo=sigo,
    )


@rotas.patch("/grupos/{slug}")
def editar(slug: str, dados: GrupoEdicao, s: Session = Depends(sessao_db),
           u: Usuario = Depends(usuario_atual)) -> GrupoSaida:
    g = grupo_do_dono(s, slug, u)
    if dados.nome is not None:
        g.nome = _nome(dados.nome)
    if dados.descricao is not None:
        g.descricao = dados.descricao.strip() or None
    s.flush()
    return _saidas(s, [g])[0]


@rotas.delete("/grupos/{slug}", status_code=204)
def apagar(slug: str, s: Session = Depends(sessao_db), u: Usuario = Depends(usuario_atual)):
    s.delete(grupo_do_dono(s, slug, u))
    return Response(status_code=204)


@rotas.post("/grupos/{slug}/seguir", status_code=204)
def seguir(slug: str, s: Session = Depends(sessao_db), u: Usuario = Depends(usuario_atual)):
    g = grupo_ou_404(s, slug)
    if g.dono_id == u.id:
        raise HTTPException(422, "Você já vê os grupos que criou")
    s.execute(insert(GrupoSeguidor).values(grupo_id=g.id, usuario_id=u.id).on_conflict_do_nothing())
    return Response(status_code=204)


@rotas.delete("/grupos/{slug}/seguir", status_code=204)
def deixar_de_seguir(slug: str, s: Session = Depends(sessao_db), u: Usuario = Depends(usuario_atual)):
    g = grupo_ou_404(s, slug)
    s.execute(delete(GrupoSeguidor).where(GrupoSeguidor.grupo_id == g.id, GrupoSeguidor.usuario_id == u.id))
    return Response(status_code=204)
