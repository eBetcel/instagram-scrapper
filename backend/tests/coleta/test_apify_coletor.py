import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from agenda.coleta.apify import ApifyColetor, classificar_erro, converter_itens
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
    assert classificar_erro("This account is private") == "privado"
    assert classificar_erro("Empty or private data for provided input") is None
    assert classificar_erro("algo estranho") is None


class ClienteFalso:
    def __init__(self, itens):
        self._itens = itens
        self.entradas = []

    def iniciar(self, entrada):
        self.entradas.append(entrada)
        return "run1"

    def aguardar(self, run_id):
        assert run_id == "run1"
        return "ds1"

    def itens(self, dataset_id):
        assert dataset_id == "ds1"
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


def test_fake_coletor_filtra_e_registra():
    p1 = PostColetado("A", "", datetime(2026, 1, 1, tzinfo=UTC), [], "a")
    p2 = PostColetado("B", "", datetime(2026, 1, 1, tzinfo=UTC), [], "b")
    f = FakeColetor([p1, p2], {"b": "x", "c": "y"})
    r = f.coletar(["a", "c"], janela="1 days", limite=1)
    assert isinstance(r, ResultadoLote)
    assert r.posts == [p1] and r.erros == {"c": "y"}
    assert f.chamadas == [(["a", "c"], "1 days", 1)]
