import json
import threading
import urllib.request
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agenda.coleta.apify import (
    ApifyCliente,
    ApifyRecusou,
    ExecucaoFalhou,
    transporte_urllib,
)

TOKEN = "segredo-123"


class Falso:
    """Transporte falso: respostas em fila, registra as chamadas."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    def __call__(self, metodo, url, corpo, cabecalhos):
        self.chamadas.append((metodo, url, corpo, cabecalhos))
        return self.respostas.pop(0)


def cliente(respostas, relogio=None):
    t = Falso(respostas)
    kw = {"relogio": relogio} if relogio else {}
    return ApifyCliente(TOKEN, "user~actor", transporte=t, **kw), t


def run(status, ds="ds1"):
    return (200, {"data": {"id": "r1", "status": status, "defaultDatasetId": ds}})


def test_iniciar_posta_no_actor_e_devolve_run_id():
    c, t = cliente([(201, {"data": {"id": "r1"}})])
    assert c.iniciar({"a": 1}) == "r1"
    metodo, url, corpo, cab = t.chamadas[0]
    assert metodo == "POST"
    assert url == "https://api.apify.com/v2/acts/user~actor/runs"
    assert corpo == {"a": 1}
    assert cab["Authorization"] == f"Bearer {TOKEN}"


def test_aguardar_ate_sucesso_devolve_dataset():
    c, t = cliente([run("RUNNING"), run("RUNNING"), run("SUCCEEDED", "dsX")])
    assert c.aguardar("r1") == "dsX"
    assert len(t.chamadas) == 3
    assert t.chamadas[0][1] == "https://api.apify.com/v2/actor-runs/r1?waitForFinish=60"


@pytest.mark.parametrize("final", ["FAILED", "TIMED-OUT", "ABORTED"])
def test_aguardar_falha_levanta_execucao_falhou(final):
    c, _ = cliente([run("RUNNING"), run(final)])
    with pytest.raises(ExecucaoFalhou, match=final):
        c.aguardar("r1")


def test_aguardar_passa_do_timeout_levanta_execucao_falhou():
    tempos = iter([0.0, 100.0, 2000.0])
    c, _ = cliente([run("RUNNING")] * 5, relogio=lambda: next(tempos))
    with pytest.raises(ExecucaoFalhou, match="timeout"):
        c.aguardar("r1", timeout=timedelta(minutes=15))


def test_itens_pagina_ate_acabar():
    p1 = [{"i": n} for n in range(1000)]
    p2 = [{"i": 1000}]
    c, t = cliente([(200, p1), (200, p2)])
    assert c.itens("ds1") == p1 + p2
    assert "offset=0&limit=1000" in t.chamadas[0][1]
    assert "offset=1000&limit=1000" in t.chamadas[1][1]
    assert "format=json&clean=true" in t.chamadas[0][1]


@pytest.mark.parametrize("status", [401, 402, 403])
def test_recusa_401_402_403_levanta_apify_recusou(status):
    c, _ = cliente([(status, {"error": {}})])
    with pytest.raises(ApifyRecusou):
        c.iniciar({})


def test_5xx_propaga_erro_de_transporte():
    c, _ = cliente([(503, {})])
    with pytest.raises(RuntimeError, match="503"):
        c.iniciar({})


def test_token_nunca_aparece_na_url_nem_na_mensagem():
    for status in (401, 500):
        c, t = cliente([(status, {})])
        with pytest.raises(Exception) as e:
            c.iniciar({})
        assert TOKEN not in str(e.value)
        assert "POST" in str(e.value) and "/v2/acts/user~actor/runs" in str(e.value)
        assert TOKEN not in t.chamadas[0][1]


class _H(BaseHTTPRequestHandler):
    visto = {}

    def _responder(self):
        n = int(self.headers.get("Content-Length") or 0)
        _H.visto = {
            "auth": self.headers.get("Authorization"),
            "ctype": self.headers.get("Content-Type"),
            "corpo": self.rfile.read(n),
        }
        status = 429 if self.path == "/erro" else 201
        data = json.dumps({"ok": True}).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_POST = do_GET = _responder

    def log_message(self, *a):
        pass


@pytest.fixture
def servidor():
    s = HTTPServer(("127.0.0.1", 0), _H)
    th = threading.Thread(target=s.serve_forever, daemon=True)
    th.start()
    yield f"http://127.0.0.1:{s.server_port}"
    s.shutdown()
    s.server_close()
    th.join()


def test_transporte_urllib_envia_json_e_cabecalhos(servidor):
    cab = {"Authorization": "Bearer t"}
    status, dados = transporte_urllib("POST", servidor + "/x", {"a": 1}, cab)
    assert (status, dados) == (201, {"ok": True})
    assert _H.visto["auth"] == "Bearer t"
    assert _H.visto["ctype"] == "application/json"
    assert json.loads(_H.visto["corpo"]) == {"a": 1}


def test_transporte_urllib_devolve_status_de_erro_sem_levantar(servidor):
    status, _ = transporte_urllib("GET", servidor + "/erro", None, {})
    assert status == 429


def test_transporte_urllib_2xx_sem_json_devolve_none(servidor, monkeypatch):
    class R:
        status = 200

        def read(self):
            return b"<html>ok</html>"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: R())
    assert transporte_urllib("GET", servidor + "/x", None, {}) == (200, None)


def test_iniciar_2xx_sem_json_levanta_erro_claro():
    c, _ = cliente([(201, None)])
    with pytest.raises(RuntimeError, match="sem JSON") as e:
        c.iniciar({})
    assert TOKEN not in str(e.value)


def test_aguardar_resposta_sem_status_levanta_erro_claro():
    c, _ = cliente([(200, {"data": {"id": "r1"}})])
    with pytest.raises(RuntimeError, match="data.status"):
        c.aguardar("r1")


def test_itens_pagina_que_nao_e_lista_levanta_erro_claro():
    c, _ = cliente([(200, {"data": []})])
    with pytest.raises(RuntimeError, match="lista"):
        c.itens("ds1")
