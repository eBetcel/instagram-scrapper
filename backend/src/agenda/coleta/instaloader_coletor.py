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


def _fixado(post: instaloader.Post) -> bool:
    """`Post.is_pinned` (formato GraphQL) ou `timeline_pinned_user_ids` (formato iPhone)."""
    if post.is_pinned:
        return True
    iphone = post._node.get("iphone_struct") or {}
    return bool(iphone.get("timeline_pinned_user_ids"))


def parse_post(post: instaloader.Post) -> PostColetado:
    """Monta `PostColetado` pela API pública de `instaloader.Post`.

    Funciona tanto para o node GraphQL anônimo quanto para o node criado por
    `Post.from_iphone_struct` (usado por `Profile.get_posts()` com sessão logada).
    Vídeos (e filhos em vídeo de carrossel) contribuem com a capa.
    """
    try:
        if post.typename == "GraphSidecar":
            urls = [n.display_url for n in post.get_sidecar_nodes()]
        else:
            urls = [post.url]  # imagem, ou capa de vídeo
    except KeyError:
        urls = []
    return PostColetado(
        shortcode=post.shortcode,
        legenda=post.caption or "",
        # `date_utc` usa datetime.utcfromtimestamp (depreciado, ingênuo); `date_local` é tz-aware.
        publicado_em=post.date_local.astimezone(UTC),
        urls_imagens=urls,
        fixado=_fixado(post),
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
            # PrivateProfileNotFollowedException só é levantada por download_profile(s).
            if getattr(perfil, "is_private", False) and not getattr(perfil, "followed_by_viewer", False):
                raise PerfilPrivado(username)
            for i, post in enumerate(perfil.get_posts()):
                p = parse_post(post)
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
