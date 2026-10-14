"""Login por link mágico, com cadastro por código de convite."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from agenda.api.deps import COOKIE_SESSAO, deps_api, sessao_db, usuario_atual
from agenda.api.seguranca import consumir_convite, hash_valor, novo_token
from agenda.models import Sessao, TokenLogin, Usuario

VALIDADE_LINK = timedelta(minutes=15)
VALIDADE_SESSAO = timedelta(days=30)
LIMITES_ENVIO = ((timedelta(minutes=1), 1), (timedelta(hours=1), 5))
ASSUNTO = "Seu link de acesso à Agenda"

rotas = APIRouter(prefix="/api")


class Entrada(BaseModel):
    email: EmailStr
    convite: str | None = None
    nome: str | None = None


@rotas.post("/auth/entrar", status_code=202)
def entrar(dados: Entrada, s: Session = Depends(sessao_db), deps=Depends(deps_api)):
    email = dados.email.strip().lower()
    agora = deps.relogio()
    usuario = s.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is None:
        if not dados.convite:
            return JSONResponse(
                {"detail": "Este e-mail ainda não tem conta: informe um código de convite.",
                 "precisa_convite": True},
                status_code=409,
            )
        nome = (dados.nome or "").strip()
        if not 1 <= len(nome) <= 60:
            raise HTTPException(422, "Informe seu nome")
        if not consumir_convite(s, dados.convite, agora):
            raise HTTPException(422, "Código de convite inválido")
        usuario = Usuario(email=email, nome=nome)
        s.add(usuario)
        s.flush()
    for janela, maximo in LIMITES_ENVIO:
        recentes = s.scalar(
            select(func.count()).select_from(TokenLogin)
            .where(TokenLogin.usuario_id == usuario.id, TokenLogin.criado_em > agora - janela)
        )
        if recentes >= maximo:
            raise HTTPException(429, "Aguarde para pedir outro link")
    token = novo_token()
    s.add(TokenLogin(usuario_id=usuario.id, token_hash=hash_valor(token),
                     expira_em=agora + VALIDADE_LINK, criado_em=agora))
    s.flush()
    link = f"{deps.config.app_url}/api/auth/verificar?token={token}"
    deps.enviador.enviar(email, ASSUNTO, (
        f"Olá, {usuario.nome}!\n\nPara entrar na Agenda, abra o link abaixo:\n\n{link}\n\n"
        "O link vale por 15 minutos e só pode ser usado uma vez."
    ))
    return {"detail": "Link enviado"}


@rotas.get("/auth/verificar")
def verificar(token: str = "", s: Session = Depends(sessao_db), deps=Depends(deps_api)):
    agora = deps.relogio()
    t = s.scalar(
        select(TokenLogin).where(TokenLogin.token_hash == hash_valor(token)).with_for_update()
    )
    if t is None or t.usado_em is not None or t.expira_em <= agora:
        return RedirectResponse("/entrar?erro=link", status_code=303)
    t.usado_em = agora
    valor = novo_token()
    s.add(Sessao(usuario_id=t.usuario_id, token_hash=hash_valor(valor),
                 expira_em=agora + VALIDADE_SESSAO))
    r = RedirectResponse("/", status_code=303)
    r.set_cookie(
        COOKIE_SESSAO, valor, max_age=int(VALIDADE_SESSAO.total_seconds()), httponly=True,
        samesite="lax", secure=deps.config.cookie_seguro, path="/",
    )
    return r


@rotas.post("/auth/sair", status_code=204)
def sair(request: Request, s: Session = Depends(sessao_db), _: Usuario = Depends(usuario_atual)):
    token = request.cookies.get(COOKIE_SESSAO, "")
    s.execute(delete(Sessao).where(Sessao.token_hash == hash_valor(token)))
    r = Response(status_code=204)
    r.delete_cookie(COOKIE_SESSAO, path="/")
    return r


@rotas.get("/eu")
def eu(u: Usuario = Depends(usuario_atual)) -> dict:
    return {"id": u.id, "email": u.email, "nome": u.nome}
