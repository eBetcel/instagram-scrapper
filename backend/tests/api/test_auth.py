import re
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from apoio import logar
from sqlalchemy import select, update

from agenda.api.seguranca import criar_convite
from agenda.models import Convite, TokenLogin, Usuario

AGORA = datetime.now(UTC)


def _convite(api, usos=1, dias=None):
    with api.fabrica() as s:
        c = criar_convite(s, usos=usos, dias=dias, agora=AGORA)
        s.commit()
    return c


def _entrar(api, email, **kw):
    return api.cliente.post("/api/auth/entrar", json={"email": email, **kw})


def _token_do_email(api):
    _, _, texto = api.enviador.enviados[-1]
    url = re.search(r"http://localhost:3000/api/auth/verificar\?token=\S+", texto).group(0)
    return parse_qs(urlparse(url).query)["token"][0]


def _usuarios(api):
    with api.fabrica() as s:
        return list(s.scalars(select(Usuario.email)))


def test_email_existente_recebe_link(api):
    logar(api, "fulana@x.com")
    api.cliente.cookies.clear()
    r = _entrar(api, "fulana@x.com")
    assert r.status_code == 202
    para, assunto, texto = api.enviador.enviados[-1]
    assert para == "fulana@x.com" and assunto == "Seu link de acesso à Agenda"
    assert "http://localhost:3000/api/auth/verificar?token=" in texto and "15 minutos" in texto


def test_email_novo_sem_convite_pede_convite(api):
    r = _entrar(api, "nova@x.com")
    assert r.status_code == 409 and r.json()["precisa_convite"] is True
    assert api.enviador.enviados == []


def test_email_novo_com_convite_sem_nome(api):
    r = _entrar(api, "nova@x.com", convite=_convite(api))
    assert r.status_code == 422 and r.json()["detail"] == "Informe seu nome"


def test_email_novo_com_convite_invalido(api):
    r = _entrar(api, "nova@x.com", convite="ZZZZ-ZZZZ", nome="Nova")
    assert r.status_code == 422 and r.json()["detail"] == "Código de convite inválido"
    assert _usuarios(api) == []


def test_email_novo_com_convite_valido_cria_conta(api):
    c = _convite(api, usos=2)
    r = _entrar(api, "nova@x.com", convite=c, nome="  Nova  ")
    assert r.status_code == 202
    with api.fabrica() as s:
        u = s.scalars(select(Usuario)).one()
        assert (u.email, u.nome) == ("nova@x.com", "Nova")
        assert s.scalar(select(Convite.usos_restantes)) == 1
    assert len(api.enviador.enviados) == 1


def test_convite_de_um_uso_nao_serve_para_segundo_email(api):
    c = _convite(api, usos=1)
    assert _entrar(api, "a@x.com", convite=c, nome="A").status_code == 202
    r = _entrar(api, "b@x.com", convite=c, nome="B")
    assert r.status_code == 422
    assert _usuarios(api) == ["a@x.com"]


def test_email_com_caixa_e_espacos_e_a_mesma_conta(api):
    _entrar(api, "  Fulano@X.com ", convite=_convite(api), nome="Fulano")
    with api.fabrica() as s:
        s.execute(update(TokenLogin).values(criado_em=AGORA - timedelta(minutes=2)))
        s.commit()
    assert _entrar(api, "fulano@x.com").status_code == 202
    assert _usuarios(api) == ["fulano@x.com"]


def test_email_invalido_da_422(api):
    assert _entrar(api, "nao-e-email").status_code == 422


def test_segundo_pedido_no_mesmo_minuto_da_429(api):
    logar(api, "fulana@x.com")
    assert _entrar(api, "fulana@x.com").status_code == 202
    r = _entrar(api, "fulana@x.com")
    assert r.status_code == 429 and r.json()["detail"] == "Aguarde para pedir outro link"


def test_sexto_pedido_na_hora_da_429(api):
    logar(api, "fulana@x.com")
    for _ in range(5):
        assert _entrar(api, "fulana@x.com").status_code == 202
        with api.fabrica() as s:
            s.execute(update(TokenLogin).values(criado_em=AGORA - timedelta(minutes=5)))
            s.commit()
    assert _entrar(api, "fulana@x.com").status_code == 429


def test_verificar_cria_sessao_e_redireciona(api):
    logar(api, "fulana@x.com")
    api.cliente.cookies.clear()
    _entrar(api, "fulana@x.com")
    token = _token_do_email(api)
    r = api.cliente.get(f"/api/auth/verificar?token={token}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    cookie = r.headers["set-cookie"].lower()
    assert "sessao=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert "secure" not in cookie
    assert api.cliente.get("/api/eu").status_code == 200


def test_token_usado_ou_vencido_volta_para_entrar(api):
    logar(api, "fulana@x.com")
    api.cliente.cookies.clear()
    _entrar(api, "fulana@x.com")
    token = _token_do_email(api)
    api.cliente.get(f"/api/auth/verificar?token={token}", follow_redirects=False)
    api.cliente.cookies.clear()
    r = api.cliente.get(f"/api/auth/verificar?token={token}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/entrar?erro=link"
    with api.fabrica() as s:
        s.execute(update(TokenLogin).values(criado_em=AGORA - timedelta(minutes=2)))
        s.commit()
    _entrar(api, "fulana@x.com")
    novo = _token_do_email(api)
    with api.fabrica() as s:
        s.execute(update(TokenLogin).where(TokenLogin.usado_em.is_(None))
                  .values(expira_em=AGORA - timedelta(seconds=1)))
        s.commit()
    r = api.cliente.get(f"/api/auth/verificar?token={novo}", follow_redirects=False)
    assert r.headers["location"] == "/entrar?erro=link"


def test_token_vale_15_minutos(api):
    logar(api, "fulana@x.com")
    _entrar(api, "fulana@x.com")
    with api.fabrica() as s:
        t = s.scalars(select(TokenLogin)).one()
        assert timedelta(minutes=14) < t.expira_em - t.criado_em <= timedelta(minutes=15, seconds=5)


def test_sair_encerra_sessao(api):
    logar(api)
    assert api.cliente.post("/api/auth/sair").status_code == 204
    assert api.cliente.get("/api/eu").status_code == 401
