"""Ajudantes dos testes da api."""

from datetime import UTC, datetime, timedelta

from agenda.api.seguranca import hash_valor, novo_token
from agenda.models import Sessao, Usuario


def logar(api, email="fulana@x.com", nome="Fulana", cliente=None) -> Usuario:
    """Cria usuário e sessão direto no banco e põe o cookie no cliente."""
    token = novo_token()
    with api.fabrica() as s:
        u = Usuario(email=email, nome=nome)
        s.add(u)
        s.flush()
        s.add(Sessao(usuario_id=u.id, token_hash=hash_valor(token),
                     expira_em=datetime.now(UTC) + timedelta(days=30)))
        s.commit()
    (cliente or api.cliente).cookies.set("sessao", token)
    return u
