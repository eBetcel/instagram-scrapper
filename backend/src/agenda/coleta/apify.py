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
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import timedelta
from typing import Any

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
