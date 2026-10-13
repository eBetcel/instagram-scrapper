import logging
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import instaloader

from agenda.coleta.base import (
    MAX_FIXADOS,
    ContaBloqueada,
    PerfilInexistente,
    PerfilPrivado,
    PostColetado,
)
from agenda.coleta.pool import PoolContas, decifrar_sessao
from agenda.models import ContaColeta

log = logging.getLogger(__name__)

BLOQUEIO = timedelta(hours=6)
_SINAIS_BLOQUEIO = ("401", "429", "checkpoint", "please wait")


def parse_post(node: dict) -> PostColetado:
    """Lê o dict `Post._node` do instaloader (ver tests/fixtures/ig/README.md).

    Fixado = `pinned_for_users` não vazio (mesmo critério de `Post.is_pinned`).
    """
    if node.get("__typename") == "GraphSidecar":
        urls = [e["node"]["display_url"] for e in node["edge_sidecar_to_children"]["edges"]]
    elif node.get("display_url"):
        urls = [node["display_url"]]  # imagem, ou capa de vídeo
    else:
        urls = []
    edges = (node.get("edge_media_to_caption") or {}).get("edges") or []
    legenda = edges[0]["node"]["text"] if edges else ""
    return PostColetado(
        shortcode=node["shortcode"],
        legenda=legenda or "",
        publicado_em=datetime.fromtimestamp(node["taken_at_timestamp"], UTC),
        urls_imagens=urls,
        fixado=bool(node.get("pinned_for_users")),
    )


def _e_bloqueio(exc: Exception) -> bool:
    if isinstance(exc, (instaloader.LoginRequiredException, instaloader.TooManyRequestsException)):
        return True
    if isinstance(exc, instaloader.ConnectionException):
        msg = str(exc).lower()
        return any(sinal in msg for sinal in _SINAIS_BLOQUEIO)
    return False


def _fabrica_real(chave: str) -> Callable[[ContaColeta, str], Any]:
    def fabrica(conta: ContaColeta, username: str):
        loader = instaloader.Instaloader(quiet=True, max_connection_attempts=1)
        if conta.sessao_criptografada:
            loader.load_session(conta.usuario_ig, decifrar_sessao(conta.sessao_criptografada, chave))
        return instaloader.Profile.from_username(loader.context, username)

    return fabrica


class InstaloaderColetor:
    def __init__(
        self,
        pool: PoolContas,
        fabrica_perfil: Callable[[ContaColeta, str], Any] | None = None,
        agora: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self.pool = pool
        self._agora = agora
        if fabrica_perfil is None:
            from agenda.config import get_settings

            fabrica_perfil = _fabrica_real(get_settings().chave_sessao)
        self._fabrica = fabrica_perfil

    def posts_desde(self, username: str, desde: datetime | None) -> Iterator[PostColetado]:
        conta = self.pool.obter()
        try:
            perfil = self._fabrica(conta, username)
            for i, post in enumerate(perfil.get_posts()):
                p = parse_post(post._node)
                possivel_fixado = p.fixado or i < MAX_FIXADOS
                if desde is not None and not possivel_fixado and p.publicado_em < desde:
                    return
                yield p
        except instaloader.ProfileNotExistsException as e:
            raise PerfilInexistente(username) from e
        except instaloader.PrivateProfileNotFollowedException as e:
            raise PerfilPrivado(username) from e
        except Exception as e:
            if _e_bloqueio(e):
                log.error("conta %s bloqueada pelo Instagram: %s", conta.usuario_ig, e)
                self.pool.marcar_bloqueada(conta, self._agora() + BLOQUEIO)
                raise ContaBloqueada(conta.usuario_ig) from e
            raise
