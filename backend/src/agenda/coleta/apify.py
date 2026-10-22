"""Cliente REST mínimo da Apify (execução de actors e leitura de datasets).

Assinatura do transporte (injetável, para testes sem rede):

    Transporte = Callable[[str, str, dict | None, dict[str, str]], tuple[int, Any]]
    (método, URL completa, corpo JSON ou None, cabeçalhos) -> (status HTTP, JSON)

O transporte devolve o status também para 4xx/5xx; erros de rede propagam.
O token vai só no cabeçalho ``Authorization: Bearer``, nunca na URL nem nas
mensagens de erro.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from agenda.coleta.base import PostColetado, ResultadoLote

log = logging.getLogger(__name__)

Transporte = Callable[[str, str, "dict | None", "dict[str, str]"], "tuple[int, Any]"]

BASE = "https://api.apify.com"
_PAGINA = 1000
_FINAIS_RUIM = {"FAILED", "TIMED-OUT", "ABORTED"}


class ApifyRecusou(Exception):
    """Apify recusou a chamada (401/402/403: token, saldo ou permissão)."""


class ExecucaoFalhou(Exception):
    """A execução do actor terminou sem sucesso ou estourou o timeout."""


def transporte_urllib(
    metodo: str, url: str, corpo: dict | None, cabecalhos: dict[str, str]
) -> tuple[int, Any]:
    dados = json.dumps(corpo).encode() if corpo is not None else None
    cab = {**cabecalhos, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=dados, headers=cab, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            status, bruto = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        status, bruto = e.code, e.read()
    try:
        return status, json.loads(bruto) if bruto else None
    except ValueError:
        return status, None


class ApifyCliente:
    def __init__(
        self,
        token: str,
        actor_id: str,
        *,
        transporte: Transporte = transporte_urllib,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self._token = token
        self._actor_id = actor_id
        self._transporte = transporte
        self._relogio = relogio

    def _chamar(self, metodo: str, caminho: str, corpo: dict | None = None) -> Any:
        cab = {"Authorization": f"Bearer {self._token}"}
        status, dados = self._transporte(metodo, BASE + caminho, corpo, cab)
        if status in (401, 402, 403):
            raise ApifyRecusou(f"Apify recusou {metodo} {caminho}: HTTP {status}")
        if status >= 400:
            raise RuntimeError(f"Apify {metodo} {caminho} falhou: HTTP {status}")
        if dados is None:
            raise RuntimeError(f"Apify {metodo} {caminho}: resposta sem JSON")
        return dados

    def _campo(self, dados: Any, chaves: tuple[str, ...], metodo: str, caminho: str):
        atual = dados
        for k in chaves:
            if not isinstance(atual, dict) or k not in atual:
                raise RuntimeError(
                    f"Apify {metodo} {caminho}: resposta sem o campo {'.'.join(chaves)}"
                )
            atual = atual[k]
        return atual

    def iniciar(self, entrada: dict) -> str:
        caminho = f"/v2/acts/{self._actor_id}/runs"
        dados = self._chamar("POST", caminho, entrada)
        return self._campo(dados, ("data", "id"), "POST", caminho)

    def aguardar(
        self, run_id: str, *, timeout: timedelta = timedelta(minutes=15)
    ) -> str:
        inicio = self._relogio()
        while True:
            caminho = f"/v2/actor-runs/{run_id}?waitForFinish=60"
            dados = self._chamar("GET", caminho)
            status = self._campo(dados, ("data", "status"), "GET", caminho)
            if status == "SUCCEEDED":
                return self._campo(
                    dados, ("data", "defaultDatasetId"), "GET", caminho
                )
            if status in _FINAIS_RUIM:
                raise ExecucaoFalhou(f"execução {run_id} terminou com {status}")
            if self._relogio() - inicio > timeout.total_seconds():
                raise ExecucaoFalhou(
                    f"timeout aguardando a execução {run_id} (último status {status})"
                )

    def itens(self, dataset_id: str) -> list[dict]:
        todos: list[dict] = []
        while True:
            caminho = (
                f"/v2/datasets/{dataset_id}/items?format=json&clean=true"
                f"&offset={len(todos)}&limit={_PAGINA}"
            )
            pagina = self._chamar("GET", caminho)
            if not isinstance(pagina, list):
                raise RuntimeError(f"Apify GET {caminho}: página não é uma lista")
            todos.extend(pagina)
            if len(pagina) < _PAGINA:
                return todos


def classificar_erro(mensagem: str) -> Literal["privado", "inexistente"] | None:
    """Classifica a mensagem guardada em ``ResultadoLote.erros``.

    Apify não dá sinal confiável de perfil privado ("Empty or private data" é
    ambíguo), então "privado" nunca é devolvido por este caminho.
    """
    m = mensagem.lower()
    if "does not exist" in m or m.strip() == "not_found":
        return "inexistente"
    return None


def _username_do_erro(item: dict) -> str | None:
    if item.get("username"):
        return str(item["username"]).lower()
    for chave in ("inputUrl", "url"):
        url = item.get(chave)
        if url:
            seg = str(url).rstrip("/").rsplit("/", 1)[-1]
            if seg:
                return seg.lower()
    return None


def converter_itens(itens: list[dict], usernames: list[str]) -> ResultadoLote:
    """Converte itens do dataset em posts agrupados por perfil pedido.

    Atribuição: ``ownerUsername`` (minúsculo) se foi pedido; senão o primeiro
    pedido presente em ``coauthorProducers[].username``; senão descarta (WARNING).
    Itens ``no_items`` são descartados (INFO). Os demais itens com ``error``
    entram em ``erros[username]`` com o texto de ``errorDescription`` (ou o
    código ``error`` se não houver), que ``classificar_erro`` sabe interpretar.
    """
    pedidos = {u.lower() for u in usernames}
    resultado = ResultadoLote()
    vistos: set[str] = set()
    for item in itens:
        erro = item.get("error")
        if erro:
            alvo = _username_do_erro(item)
            if erro == "no_items":
                log.info("sem posts novos (ou perfil privado) para %s", alvo)
            elif alvo:
                resultado.erros[alvo] = str(item.get("errorDescription") or erro)
            else:
                log.warning("item de erro sem username identificável: %s", erro)
            continue
        shortcode = item.get("shortCode")
        timestamp = item.get("timestamp")
        if not shortcode or not timestamp:
            log.warning("item descartado sem shortCode/timestamp: %s", shortcode)
            continue
        dono = str(item.get("ownerUsername") or "").lower()
        perfil = dono if dono in pedidos else None
        if perfil is None:
            for co in item.get("coauthorProducers") or []:
                nome = str(co.get("username") or "").lower()
                if nome in pedidos:
                    perfil = nome
                    break
        if perfil is None:
            log.warning("post %s de %r não pertence a perfil pedido", shortcode, dono)
            continue
        if shortcode in vistos:
            continue
        try:
            publicado_em = datetime.fromisoformat(timestamp).astimezone(UTC)
        except (ValueError, TypeError):
            log.warning("post %s descartado: timestamp inválido %r", shortcode, timestamp)
            continue
        vistos.add(shortcode)
        imagens = item.get("images") or (
            [item["displayUrl"]] if item.get("displayUrl") else []
        )
        resultado.posts.append(
            PostColetado(
                shortcode=shortcode,
                legenda=item.get("caption") or "",
                publicado_em=publicado_em,
                urls_imagens=list(imagens),
                perfil=perfil,
            )
        )
    return resultado


class ApifyColetor:
    def __init__(self, cliente: ApifyCliente) -> None:
        self._cliente = cliente

    def coletar(
        self, usernames: list[str], *, janela: str, limite: int
    ) -> ResultadoLote:
        entrada = {
            "username": list(usernames),
            "onlyPostsNewerThan": janela,
            "resultsLimit": limite,
            "skipPinnedPosts": True,
            "dataDetailLevel": "basicData",
        }
        run_id = self._cliente.iniciar(entrada)
        dataset_id = self._cliente.aguardar(run_id)
        resultado = converter_itens(self._cliente.itens(dataset_id), usernames)
        resultado.run_ids = [run_id]
        return resultado
