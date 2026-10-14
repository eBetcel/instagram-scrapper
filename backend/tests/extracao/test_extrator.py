import base64
import io
import json
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from openai import APITimeoutError, LengthFinishReasonError
from openai.lib._pydantic import to_strict_json_schema
from PIL import Image

from agenda.extracao.extrator import (
    FakeExtrator,
    OpenAIExtrator,
    RespostaInvalida,
    Uso,
    calcular_custo,
)
from agenda.extracao.schema import ExtracaoPost

FIXTURES = Path(__file__).parent.parent / "fixtures" / "openai"
PUBLICADO = datetime(2026, 11, 1, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


def _fixture(nome: str) -> ExtracaoPost:
    return ExtracaoPost.model_validate(json.loads((FIXTURES / nome).read_text()))


def _resp(parsed=None, refusal=None, entrada=100, saida=50):
    msg = SimpleNamespace(parsed=parsed, refusal=refusal)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=msg)],
        usage=SimpleNamespace(prompt_tokens=entrada, completion_tokens=saida),
    )


class ClienteFalso:
    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.chamadas: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self._parse))

    def _parse(self, **kwargs):
        self.chamadas.append(kwargs)
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _jpeg(lado=3000) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (lado, lado // 2), "red").save(buf, "JPEG")
    return buf.getvalue()


def test_sdk_aceita_o_schema():
    esquema = to_strict_json_schema(ExtracaoPost)
    assert esquema["type"] == "object"
    assert "eventos" in esquema["required"]


def test_extrai_varios_eventos_de_um_flyer():
    cliente = ClienteFalso(_resp(_fixture("extracao_varios_eventos.json")))
    r = OpenAIExtrator(cliente, "gpt-4.1-mini").extrair("legenda", [_jpeg()], "casa", PUBLICADO)
    assert [e.titulo for e in r.extracao.eventos] == ["Noite do Samba", "Roda de Choro"]
    assert r.uso == Uso(
        tokens_entrada=100, tokens_saida=50, custo=calcular_custo("gpt-4.1-mini", 100, 50),
        modelo="gpt-4.1-mini",
    )
    assert cliente.chamadas[0]["response_format"] is ExtracaoPost
    assert cliente.chamadas[0]["model"] == "gpt-4.1-mini"
    # Determinístico: com a temperatura padrão (1,0) o mesmo post recebia decisões diferentes.
    assert cliente.chamadas[0]["temperature"] == 0


def test_post_sem_evento_retorna_lista_vazia():
    cliente = ClienteFalso(_resp(_fixture("extracao_vazia.json")))
    r = OpenAIExtrator(cliente, "gpt-4.1-mini").extrair("bom dia", [], "casa", PUBLICADO)
    assert r.extracao.eventos == []


def test_resposta_invalida_tenta_de_novo_e_depois_levanta():
    cliente = ClienteFalso(
        _resp(refusal="não posso", entrada=10, saida=1), _resp(parsed=None, entrada=20, saida=2)
    )
    with pytest.raises(RespostaInvalida) as exc:
        OpenAIExtrator(cliente, "gpt-4.1-mini").extrair("x", [], "casa", PUBLICADO)
    assert len(cliente.chamadas) == 2
    assert exc.value.uso == Uso(30, 3, calcular_custo("gpt-4.1-mini", 30, 3), "gpt-4.1-mini")


def test_falha_por_erro_de_parse_soma_uso_da_completion():
    erro = LengthFinishReasonError(
        completion=SimpleNamespace(usage=SimpleNamespace(prompt_tokens=7, completion_tokens=5))
    )
    cliente = ClienteFalso(erro, _resp(parsed=None, entrada=1, saida=1))
    with pytest.raises(RespostaInvalida) as exc:
        OpenAIExtrator(cliente, "gpt-4.1-mini").extrair("x", [], "casa", PUBLICADO)
    assert (exc.value.uso.tokens_entrada, exc.value.uso.tokens_saida) == (8, 6)


def test_segunda_tentativa_valida_soma_uso():
    cliente = ClienteFalso(
        _resp(parsed=None, entrada=10, saida=1),
        _resp(_fixture("extracao_vazia.json"), entrada=20, saida=2),
    )
    r = OpenAIExtrator(cliente, "gpt-4.1-mini").extrair("x", [], "casa", PUBLICADO)
    assert (r.uso.tokens_entrada, r.uso.tokens_saida) == (30, 3)
    assert r.uso.custo == calcular_custo("gpt-4.1-mini", 30, 3)


def test_erro_de_parse_do_sdk_conta_como_invalido():
    erro = LengthFinishReasonError(completion=SimpleNamespace(usage=None))
    cliente = ClienteFalso(erro, _resp(_fixture("extracao_vazia.json")))
    r = OpenAIExtrator(cliente, "gpt-4.1-mini").extrair("x", [], "casa", PUBLICADO)
    assert r.extracao.eventos == []
    assert len(cliente.chamadas) == 2


def test_erro_de_transporte_propaga_sem_retentar():
    import httpx2 as httpx

    erro = APITimeoutError(request=httpx.Request("POST", "http://x"))
    cliente = ClienteFalso(erro)
    with pytest.raises(APITimeoutError):
        OpenAIExtrator(cliente, "gpt-4.1-mini").extrair("x", [], "casa", PUBLICADO)
    assert len(cliente.chamadas) == 1


def test_envia_imagens_redimensionadas():
    cliente = ClienteFalso(_resp(_fixture("extracao_vazia.json")))
    OpenAIExtrator(cliente, "m").extrair("Show sexta", [_jpeg(), _jpeg()], "casa", PUBLICADO)
    msgs = cliente.chamadas[0]["messages"]
    assert msgs[0]["role"] == "system"
    partes = msgs[1]["content"]
    assert partes[0]["type"] == "text"
    assert "casa" in partes[0]["text"] and "Show sexta" in partes[0]["text"]
    assert "2026-11-01" in partes[0]["text"]
    imagens = [p for p in partes if p["type"] == "image_url"]
    assert len(imagens) == 2
    prefixo = "data:image/jpeg;base64,"
    for p in imagens:
        url = p["image_url"]["url"]
        assert url.startswith(prefixo)
        img = Image.open(io.BytesIO(base64.b64decode(url[len(prefixo):])))
        assert max(img.size) <= 1024


def test_post_sem_imagens_envia_so_legenda():
    cliente = ClienteFalso(_resp(_fixture("extracao_vazia.json")))
    OpenAIExtrator(cliente, "m").extrair("só texto", [], "casa", PUBLICADO)
    partes = cliente.chamadas[0]["messages"][1]["content"]
    assert [p["type"] for p in partes] == ["text"]
    assert "só texto" in partes[0]["text"]


def test_calcula_custo_pelos_tokens():
    assert calcular_custo("gpt-4.1-mini", 1_000_000, 1_000_000) == Decimal("2.00")
    assert calcular_custo("gpt-4.1-nano", 500_000, 0) == Decimal("0.05")


def test_modelo_desconhecido_custa_zero_e_avisa(caplog):
    with caplog.at_level(logging.WARNING):
        assert calcular_custo("modelo-x", 1000, 1000) == Decimal(0)
    assert "modelo-x" in caplog.text


def test_fake_extrator_por_username():
    ev = _fixture("extracao_varios_eventos.json")
    fake = FakeExtrator({"casa": ev})
    r = fake.extrair("l", [], "casa", PUBLICADO)
    assert r.extracao == ev
    assert r.uso == Uso(tokens_entrada=0, tokens_saida=0, custo=Decimal(0), modelo="fake")
    assert fake.extrair("l", [], "outra", PUBLICADO).extracao.eventos == []
