import base64
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from openai import ContentFilterFinishReasonError, LengthFinishReasonError
from pydantic import ValidationError

from agenda.config import PRECOS_POR_MILHAO
from agenda.extracao.regras import instrucoes_datas
from agenda.extracao.schema import ExtracaoPost
from agenda.imagens import redimensionar

log = logging.getLogger(__name__)

TENTATIVAS = 2

PROMPT_SISTEMA = """\
Você extrai eventos culturais de posts de Instagram (legenda e imagens de flyers) \
de perfis de casas de show, teatros, galerias e produtores no Brasil.

Regras:
- Um post pode divulgar vários eventos (por exemplo, uma programação mensal): \
devolva um item em `eventos` para cada evento. Se o post não divulga nenhum \
evento, devolva a lista vazia.
- Não invente o que não está no post. Se uma informação não aparece na legenda \
nem nas imagens, use null (ou lista vazia em `artistas`).
- `categoria` deve ser exatamente uma de: show, festa, exposicao, teatro, \
cinema, oficina, festival, outro. Na dúvida, use "outro".
- `cidade` é obrigatória sempre que puder ser inferida do post (endereço, \
local conhecido, hashtags ou perfil); caso contrário, null.
- Datas no formato ISO (AAAA-MM-DD) e horas no formato HH:MM:SS, no fuso de \
São Paulo. Resolva datas relativas ("sexta que vem", "amanhã") a partir da \
data de publicação informada.
- `gratuito` é true apenas se o post disser explicitamente que a entrada é \
gratuita; preços em reais, como número.
- `status_indicado` só é preenchido se o post disser que o evento foi \
adiado, cancelado ou esgotado.
- `confianca` traz, de 0 a 1, o quanto você confia em `data_inicio`, \
`hora_inicio` e `local_nome`: valores baixos quando o dado foi deduzido, \
estiver ilegível ou ausente.
"""


@dataclass(frozen=True)
class Uso:
    tokens_entrada: int
    tokens_saida: int
    custo: Decimal
    modelo: str


@dataclass(frozen=True)
class Resultado:
    extracao: ExtracaoPost
    uso: Uso


class RespostaInvalida(Exception):
    pass


class Extrator(Protocol):
    def extrair(
        self, legenda: str, imagens: list[bytes], username: str, publicado_em: datetime
    ) -> Resultado: ...


def calcular_custo(modelo: str, tokens_entrada: int, tokens_saida: int) -> Decimal:
    precos = PRECOS_POR_MILHAO.get(modelo)
    if precos is None:
        log.warning("Modelo %r sem preço configurado; custo estimado = 0", modelo)
        return Decimal(0)
    entrada, saida = precos
    return (entrada * tokens_entrada + saida * tokens_saida) / Decimal(1_000_000)


def _tokens(usage: Any) -> tuple[int, int]:
    if usage is None:
        return 0, 0
    return usage.prompt_tokens, usage.completion_tokens


class OpenAIExtrator:
    def __init__(self, client: Any, modelo: str):
        self.client = client
        self.modelo = modelo

    def _mensagens(
        self, legenda: str, imagens: list[bytes], username: str, publicado_em: datetime
    ) -> list[dict[str, Any]]:
        texto = (
            f"Perfil: @{username}\n"
            f"Publicado em: {publicado_em.isoformat()}\n"
            f"{instrucoes_datas(publicado_em)}\n\n"
            f"Legenda:\n{legenda}"
        )
        partes: list[dict[str, Any]] = [{"type": "text", "text": texto}]
        for dados in imagens:
            b64 = base64.b64encode(redimensionar(dados)).decode("ascii")
            partes.append(
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            )
        return [
            {"role": "system", "content": PROMPT_SISTEMA},
            {"role": "user", "content": partes},
        ]

    def extrair(
        self, legenda: str, imagens: list[bytes], username: str, publicado_em: datetime
    ) -> Resultado:
        mensagens = self._mensagens(legenda, imagens, username, publicado_em)
        entrada = saida = 0
        for tentativa in range(1, TENTATIVAS + 1):
            try:
                resp = self.client.chat.completions.parse(
                    model=self.modelo, messages=mensagens, response_format=ExtracaoPost
                )
            except (ValidationError, LengthFinishReasonError, ContentFilterFinishReasonError) as e:
                completion = getattr(e, "completion", None)
                e_in, e_out = _tokens(getattr(completion, "usage", None))
                entrada += e_in
                saida += e_out
                log.warning("Resposta inválida (tentativa %d): %s", tentativa, type(e).__name__)
                continue
            e_in, e_out = _tokens(resp.usage)
            entrada += e_in
            saida += e_out
            msg = resp.choices[0].message
            if msg.refusal or msg.parsed is None:
                log.warning("Resposta inválida (tentativa %d): recusa ou sem parsed", tentativa)
                continue
            uso = Uso(entrada, saida, calcular_custo(self.modelo, entrada, saida), self.modelo)
            return Resultado(msg.parsed, uso)
        raise RespostaInvalida(f"resposta inválida após {TENTATIVAS} tentativas")


class FakeExtrator:
    def __init__(self, respostas: dict[str, ExtracaoPost]):
        self.respostas = respostas

    def extrair(
        self, legenda: str, imagens: list[bytes], username: str, publicado_em: datetime
    ) -> Resultado:
        extracao = self.respostas.get(username, ExtracaoPost(eventos=[]))
        return Resultado(extracao, Uso(0, 0, Decimal(0), "fake"))
