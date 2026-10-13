import json
import logging
from typing import Any, Literal, Protocol, get_args

from pydantic import BaseModel, ConfigDict

from agenda.extracao.extrator import Uso, parse_com_retentativa
from agenda.extracao.schema import EventoExtraido
from agenda.models import Evento, Post

log = logging.getLogger(__name__)

Campo = Literal[
    "titulo", "descricao", "inicio", "fim", "local_nome", "endereco", "cidade", "categoria",
    "preco_texto", "gratuito", "preco_min", "preco_max", "link_ingresso", "artistas", "status",
]
CAMPOS_PERMITIDOS: frozenset[str] = frozenset(get_args(Campo))

PROMPT_RECONCILIACAO = """\
Você decide se um evento cultural extraído de um post de Instagram é um evento \
NOVO, um DUPLICADO de um evento já cadastrado ou uma ATUALIZACAO de um evento \
já cadastrado.

Você recebe o evento extraído (JSON), a legenda original, o @ do autor, a data \
de publicação do post e uma lista de candidatos já cadastrados, cada um com seu \
`id` e seus campos atuais.

Decisões:
- NOVO: nenhum candidato é o mesmo evento. Use `evento_id` null.
- DUPLICADO: um candidato é o mesmo evento e o post não muda nada nele (pode \
apenas trazer dados que faltavam). `evento_id` é o `id` desse candidato.
- ATUALIZACAO: um candidato é o mesmo evento e o post muda algo nele (nova \
data, novo local, preço, adiamento, cancelamento, ingressos esgotados etc.). \
`evento_id` é o `id` desse candidato e `mudancas` lista os nomes dos campos \
alterados; os novos valores são os do evento extraído.

Regras:
- `evento_id` deve ser, obrigatoriamente, o `id` de um dos candidatos enviados.
- Mesmo título com local ou data-base diferentes, e sem nenhuma pista de \
remarcação (adiamento, nova data, mudança de local), NÃO é duplicado: é um \
evento NOVO (por exemplo, uma turnê ou uma programação que se repete).
- Dois shows com artistas diferentes no mesmo local e no mesmo dia são eventos \
distintos: NÃO é duplicado.
- Em `mudancas`, inclua só campos cujo valor no evento extraído é diferente do \
valor atual do candidato; nunca inclua campos que o post não informa. Em \
DUPLICADO e NOVO, use a lista vazia.
- `motivo` é uma frase curta explicando a decisão.
"""


class Decisao(BaseModel):
    """Compativel com structured outputs estritos (R22)."""

    model_config = ConfigDict(extra="forbid")

    decisao: Literal["NOVO", "DUPLICADO", "ATUALIZACAO"]
    evento_id: int | None
    mudancas: list[Campo]
    motivo: str


class DecisaoInvalida(Exception):
    pass


class Reconciliador(Protocol):
    def decidir(
        self, e: EventoExtraido, candidatos: list[Evento], post: Post
    ) -> tuple[Decisao, Uso | None]: ...


def evento_id_valido(d: Decisao, candidatos: list[Evento]) -> bool:
    if d.decisao == "NOVO":
        return True
    return d.evento_id is not None and d.evento_id in {c.id for c in candidatos}


def _candidato_json(c: Evento) -> dict[str, Any]:
    def iso(v):
        return v.isoformat() if v is not None else None

    def num(v):
        return str(v) if v is not None else None

    return {
        "id": c.id,
        "titulo": c.titulo,
        "descricao": c.descricao,
        "inicio": iso(c.inicio),
        "hora_definida": c.hora_definida,
        "fim": iso(c.fim),
        "local_nome": c.local_nome,
        "endereco": c.endereco,
        "cidade": c.cidade,
        "categoria": c.categoria,
        "preco_texto": c.preco_texto,
        "gratuito": c.gratuito,
        "preco_min": num(c.preco_min),
        "preco_max": num(c.preco_max),
        "link_ingresso": c.link_ingresso,
        "artistas": list(c.artistas or []),
        "status": c.status,
    }


class OpenAIReconciliador:
    def __init__(self, client: Any, modelo: str):
        self.client = client
        self.modelo = modelo

    def _mensagens(
        self, e: EventoExtraido, candidatos: list[Evento], post: Post
    ) -> list[dict[str, Any]]:
        publicado = post.publicado_em.isoformat() if post.publicado_em else "desconhecida"
        texto = (
            f"Perfil: @{post.perfil.username}\n"
            f"Publicado em: {publicado}\n\n"
            f"Legenda:\n{post.legenda or ''}\n\n"
            f"Evento extraído:\n{json.dumps(e.model_dump(mode='json'), ensure_ascii=False)}\n\n"
            "Candidatos:\n"
            + json.dumps([_candidato_json(c) for c in candidatos], ensure_ascii=False, indent=1)
        )
        return [
            {"role": "system", "content": PROMPT_RECONCILIACAO},
            {"role": "user", "content": texto},
        ]

    def decidir(
        self, e: EventoExtraido, candidatos: list[Evento], post: Post
    ) -> tuple[Decisao, Uso | None]:
        if not candidatos:
            return Decisao(decisao="NOVO", evento_id=None, mudancas=[], motivo="sem candidatos"), None
        mensagens = self._mensagens(e, candidatos, post)

        def validar(d: Decisao) -> bool:
            if evento_id_valido(d, candidatos):
                return True
            log.warning("evento_id %r fora dos candidatos", d.evento_id)
            return False

        return parse_com_retentativa(self.client, self.modelo, mensagens, Decisao, validar)


class FakeReconciliador:
    def __init__(self, decisoes: list[Decisao]):
        self.decisoes = list(decisoes)

    def decidir(
        self, e: EventoExtraido, candidatos: list[Evento], post: Post
    ) -> tuple[Decisao, Uso | None]:
        return self.decisoes.pop(0), None
