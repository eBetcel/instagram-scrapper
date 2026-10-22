import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agenda.coleta.apify import (
    ApifyColetor,
    ExecucaoFalhou,
    ExecucaoTerminou,
    classificar_erro,
    converter_itens,
)
from agenda.coleta.base import FakeColetor, PostColetado, ResultadoLote

FIX = Path(__file__).parent.parent / "fixtures" / "apify"


def _carregar(nome):
    return json.loads((FIX / nome).read_text())


def _post(**kw):
    base = {
        "shortCode": "AAA",
        "caption": "oi",
        "timestamp": "2026-10-19T14:43:56.000Z",
        "displayUrl": "https://img/capa.jpg",
        "ownerUsername": "festivalmada",
    }
    return {**base, **kw}


def test_converte_imagem_carrossel_e_video():
    itens = [
        _post(shortCode="C", type="Sidecar", images=["u1", "u2", "u3"]),
        _post(shortCode="V", type="Video", images=[], displayUrl="capa-v"),
        _post(shortCode="S", type="Sidecar"),
        _post(shortCode="N", displayUrl=None),
    ]
    por = {p.shortcode: p for p in converter_itens(itens, ["festivalmada"]).posts}
    assert por["C"].urls_imagens == ["u1", "u2", "u3"]
    assert por["V"].urls_imagens == ["capa-v"]
    assert por["S"].urls_imagens == ["https://img/capa.jpg"]
    assert por["N"].urls_imagens == []


def test_legenda_nula_vira_vazia():
    r = converter_itens([_post(caption=None)], ["festivalmada"])
    assert r.posts[0].legenda == ""


def test_timestamp_vira_datetime_utc():
    r = converter_itens([_post()], ["festivalmada"])
    assert r.posts[0].publicado_em == datetime(2026, 10, 19, 14, 43, 56, tzinfo=UTC)


def test_item_sem_timestamp_e_descartado_com_warning(caplog):
    with caplog.at_level(logging.WARNING):
        r = converter_itens([_post(timestamp=None)], ["festivalmada"])
    assert r.posts == []
    assert any(x.levelno == logging.WARNING for x in caplog.records)


def test_item_com_error_vai_para_erros_pelo_username():
    itens = _carregar("lote_misto.json")
    r = converter_itens(itens, ["festivalmada", "perfil-que-nao-existe-agenda-xyz"])
    assert set(r.erros) == {"perfil-que-nao-existe-agenda-xyz"}
    assert classificar_erro(r.erros["perfil-que-nao-existe-agenda-xyz"]) == "inexistente"


def test_erro_pela_url_e_mensagem_da_descricao():
    item = {
        "error": "not_found",
        "errorDescription": "Profile does not exist",
        "url": "https://www.instagram.com/Joe",
    }
    r = converter_itens([item], ["joe"])
    assert r.erros == {"joe": "Profile does not exist"}


def test_no_items_e_descartado_sem_erro(caplog):
    itens = _carregar("janela_horas.json")
    with caplog.at_level(logging.INFO):
        r = converter_itens(itens, ["jazznobardenazare"])
    assert r.posts == [] and r.erros == {}
    assert any(x.levelno == logging.INFO for x in caplog.records)


def test_atribui_ao_perfil_pedido():
    itens = _carregar("lote_misto.json")
    r = converter_itens(itens, ["festivalmada", "jazznobardenazare"])
    por = {p.shortcode: p for p in r.posts}
    assert por["DewwwzJIBSC"].perfil == "festivalmada"  # dono cartolamag
    assert por["DewuoJUuaj4"].perfil == "festivalmada"  # dono toca_uol
    assert por["Deu_Pw9T8pM"].perfil == "festivalmada"  # dono direto
    assert por["DergC33RbRu"].perfil == "jazznobardenazare"
    assert len(r.posts) == 6


def test_owner_com_maiusculas_casa_com_pedido():
    r = converter_itens([_post(ownerUsername="FestivalMADA")], ["festivalmada"])
    assert r.posts[0].perfil == "festivalmada"


def test_item_de_dono_nao_pedido_e_descartado(caplog):
    item = _post(ownerUsername="outro", coauthorProducers=[{"username": "mais"}])
    with caplog.at_level(logging.WARNING):
        r = converter_itens([item], ["festivalmada"])
    assert r.posts == []
    assert any(x.levelno == logging.WARNING for x in caplog.records)


def test_mesmo_shortcode_duas_vezes_fica_uma():
    r = converter_itens([_post(), _post()], ["festivalmada"])
    assert len(r.posts) == 1


def test_classificar_erro():
    assert classificar_erro("Profile does not exist") == "inexistente"
    assert classificar_erro("not_found") == "inexistente"
    assert classificar_erro("This account is private") is None
    assert classificar_erro("Empty or private data for provided input") is None
    assert classificar_erro("algo estranho") is None


class ClienteFalso:
    """``finais``: run_id -> exceção que ``aguardar`` levanta para ele."""

    def __init__(self, itens, finais=None):
        self._itens = itens
        self._finais = finais or {}
        self.entradas = []
        self.eventos = []

    def iniciar(self, entrada):
        self.entradas.append(entrada)
        self.eventos.append(("iniciar", "run1"))
        return "run1"

    def aguardar(self, run_id):
        self.eventos.append(("aguardar", run_id))
        if run_id in self._finais:
            raise self._finais[run_id]
        return f"ds-{run_id}"

    def itens(self, dataset_id):
        self.eventos.append(("itens", dataset_id))
        return self._itens


def test_coletor_envia_entrada_fixa():
    c = ClienteFalso([])
    ApifyColetor(c).coletar(["a", "b"], janela="30 days", limite=7)
    assert c.entradas == [
        {
            "username": ["a", "b"],
            "onlyPostsNewerThan": "30 days",
            "resultsLimit": 7,
            "skipPinnedPosts": True,
            "dataDetailLevel": "basicData",
        }
    ]


def test_coletor_devolve_run_ids():
    c = ClienteFalso([_post()])
    r = ApifyColetor(c).coletar(["festivalmada"], janela="30 days", limite=3)
    assert r.run_ids == ["run1"]
    assert [p.shortcode for p in r.posts] == ["AAA"]


def test_coletor_avisa_o_run_novo_antes_de_aguardar():
    c = ClienteFalso([_post()])
    avisados = []

    def ao_iniciar(run_id):
        avisados.append(run_id)
        assert c.eventos == [("iniciar", "run1")]  # ainda não aguardou

    r = ApifyColetor(c).coletar(
        ["festivalmada"], janela="30 days", limite=3, ao_iniciar=ao_iniciar
    )
    assert avisados == ["run1"]
    assert r.run_ids == ["run1"]


def test_coletor_reaproveita_run_existente_sem_iniciar_outro():
    c = ClienteFalso([_post()])
    avisados = []
    r = ApifyColetor(c).coletar(
        ["festivalmada"], janela="30 days", limite=3, run_id="rA", ao_iniciar=avisados.append
    )
    assert c.entradas == []
    assert avisados == []
    assert c.eventos == [("aguardar", "rA"), ("itens", "ds-rA")]
    assert r.run_ids == ["rA"]
    assert [p.shortcode for p in r.posts] == ["AAA"]


@pytest.mark.parametrize("final", ["FAILED", "ABORTED", "TIMED-OUT"])
def test_coletor_troca_run_existente_que_terminou_mal(final):
    c = ClienteFalso([_post()], finais={"rA": ExecucaoTerminou("rA", final)})
    avisados = []
    r = ApifyColetor(c).coletar(
        ["festivalmada"], janela="30 days", limite=3, run_id="rA", ao_iniciar=avisados.append
    )
    assert c.eventos == [
        ("aguardar", "rA"), ("iniciar", "run1"), ("aguardar", "run1"), ("itens", "ds-run1"),
    ]
    assert avisados == ["run1"]
    assert r.run_ids == ["run1"]


def test_coletor_nao_inicia_outro_run_se_o_existente_estourou_o_prazo():
    c = ClienteFalso([], finais={"rA": ExecucaoFalhou("timeout aguardando rA; abortada")})
    with pytest.raises(ExecucaoFalhou, match="timeout"):
        ApifyColetor(c).coletar(["festivalmada"], janela="30 days", limite=3, run_id="rA")
    assert c.entradas == []


def test_fake_coletor_filtra_e_registra():
    p1 = PostColetado("A", "", datetime(2026, 1, 1, tzinfo=UTC), [], "a")
    p2 = PostColetado("B", "", datetime(2026, 1, 1, tzinfo=UTC), [], "b")
    f = FakeColetor([p1, p2], {"b": "x", "c": "y"})
    r = f.coletar(["a", "c"], janela="1 days", limite=1)
    assert isinstance(r, ResultadoLote)
    assert r.posts == [p1] and r.erros == {"c": "y"}
    assert f.chamadas == [(["a", "c"], "1 days", 1)]


def test_timestamp_invalido_nao_derruba_o_lote(caplog):
    itens = [
        _post(shortCode="X", timestamp="lixo"),
        _post(shortCode="Y", timestamp=12345),
        _post(shortCode="OK"),
    ]
    with caplog.at_level(logging.WARNING):
        r = converter_itens(itens, ["festivalmada"])
    assert [p.shortcode for p in r.posts] == ["OK"]
    assert sum(x.levelno == logging.WARNING for x in caplog.records) == 2
