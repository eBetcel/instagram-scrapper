import json
from datetime import date, time
from types import SimpleNamespace

import pytest
from fabricas import evento, extraido, post
from openai.lib._pydantic import to_strict_json_schema
from pydantic import ValidationError

from agenda.extracao.extrator import RespostaInvalida, Uso, calcular_custo
from agenda.reconciliacao.decisao import (
    PROMPT_RECONCILIACAO,
    Decisao,
    FakeReconciliador,
    OpenAIReconciliador,
)


def _resp(parsed=None, refusal=None, entrada=100, saida=20):
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


def _d(decisao="DUPLICADO", evento_id=None, mudancas=(), motivo="m"):
    return Decisao(decisao=decisao, evento_id=evento_id, mudancas=list(mudancas), motivo=motivo)


E = extraido(
    titulo="Festival Jazz na Praça", data_inicio=date(2026, 11, 20), hora_inicio=time(20, 0),
    local_nome="Praça Central", artistas=["Fulano"],
)


def test_sdk_aceita_o_schema():
    esquema = to_strict_json_schema(Decisao)
    assert set(esquema["required"]) == {"decisao", "evento_id", "mudancas", "motivo"}


def test_decisao_rejeita_campo_fora_da_lista():
    with pytest.raises(ValidationError):
        _d("ATUALIZACAO", 1, ["hora_definida"])


def test_prompt_tem_as_regras_de_nao_duplicado():
    p = PROMPT_RECONCILIACAO.lower()
    assert "remarcação" in p
    assert "artistas diferentes" in p


def test_sem_candidatos_nao_chama_api(session):
    cliente = ClienteFalso()
    d, uso = OpenAIReconciliador(cliente, "gpt-4.1-nano").decidir(E, [], post(session))
    assert d.decisao == "NOVO" and d.evento_id is None and d.mudancas == []
    assert uso is None
    assert cliente.chamadas == []


def test_envia_evento_candidatos_e_contexto_do_post(session):
    ev = evento(session, "Festival Jazz na Praça", local_nome="Praça Central", link_ingresso=None)
    p = post(session, legenda="Vem aí o festival!", username="casa_jazz")
    cliente = ClienteFalso(_resp(_d("DUPLICADO", ev.id)))
    d, uso = OpenAIReconciliador(cliente, "gpt-4.1-nano").decidir(E, [ev], p)

    assert d.evento_id == ev.id
    assert uso == Uso(100, 20, calcular_custo("gpt-4.1-nano", 100, 20), "gpt-4.1-nano")
    chamada = cliente.chamadas[0]
    assert chamada["model"] == "gpt-4.1-nano"
    assert chamada["response_format"] is Decisao
    msgs = chamada["messages"]
    assert msgs[0] == {"role": "system", "content": PROMPT_RECONCILIACAO}
    texto = msgs[1]["content"]
    assert isinstance(texto, str)  # só texto, sem imagens
    assert "@casa_jazz" in texto
    assert "Vem aí o festival!" in texto
    assert p.publicado_em.isoformat() in texto
    assert json.dumps(E.model_dump(mode="json"), ensure_ascii=False) in texto
    assert f'"id": {ev.id}' in texto
    assert '"local_nome": "Praça Central"' in texto


def test_resposta_invalida_tenta_de_novo(session):
    ev = evento(session, "Festival Jazz na Praça")
    cliente = ClienteFalso(
        _resp(refusal="não", entrada=10, saida=1), _resp(_d("DUPLICADO", ev.id), entrada=20, saida=2)
    )
    d, uso = OpenAIReconciliador(cliente, "gpt-4.1-nano").decidir(E, [ev], post(session))
    assert d.decisao == "DUPLICADO"
    assert (uso.tokens_entrada, uso.tokens_saida) == (30, 3)
    assert len(cliente.chamadas) == 2


def test_resposta_invalida_duas_vezes_levanta(session):
    ev = evento(session, "Festival Jazz na Praça")
    cliente = ClienteFalso(_resp(parsed=None, entrada=10, saida=1), _resp(parsed=None, entrada=20, saida=2))
    with pytest.raises(RespostaInvalida) as exc:
        OpenAIReconciliador(cliente, "gpt-4.1-nano").decidir(E, [ev], post(session))
    assert len(cliente.chamadas) == 2
    assert exc.value.uso == Uso(30, 3, calcular_custo("gpt-4.1-nano", 30, 3), "gpt-4.1-nano")


def test_evento_id_fora_dos_candidatos_tenta_de_novo_e_levanta(session):
    ev = evento(session, "Festival Jazz na Praça")
    cliente = ClienteFalso(_resp(_d("DUPLICADO", ev.id + 999)), _resp(_d("ATUALIZACAO", None)))
    with pytest.raises(RespostaInvalida) as exc:
        OpenAIReconciliador(cliente, "m").decidir(E, [ev], post(session))
    assert len(cliente.chamadas) == 2
    assert (exc.value.uso.tokens_entrada, exc.value.uso.tokens_saida) == (200, 40)


def test_evento_id_invalido_depois_valido(session):
    ev = evento(session, "Festival Jazz na Praça")
    cliente = ClienteFalso(_resp(_d("DUPLICADO", ev.id + 999)), _resp(_d("DUPLICADO", ev.id)))
    d, _ = OpenAIReconciliador(cliente, "m").decidir(E, [ev], post(session))
    assert d.evento_id == ev.id


def test_novo_ignora_evento_id(session):
    ev = evento(session, "Festival Jazz na Praça")
    cliente = ClienteFalso(_resp(_d("NOVO", 12345)))
    d, _ = OpenAIReconciliador(cliente, "m").decidir(E, [ev], post(session))
    assert d.decisao == "NOVO"
    assert len(cliente.chamadas) == 1


def test_fake_reconciliador_devolve_em_ordem():
    a, b = _d("NOVO"), _d("DUPLICADO", 1)
    fake = FakeReconciliador([a, b])
    assert fake.decidir(E, [], None) == (a, None)
    assert fake.decidir(E, [], None) == (b, None)
