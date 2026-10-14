import json

from apoio import logar
from fastapi.testclient import TestClient


def _criar(api, nome="Jazz em Natal", descricao=None, cliente=None):
    return (cliente or api.cliente).post("/api/grupos", json={"nome": nome, "descricao": descricao})


def _outro_cliente(api):
    return TestClient(api.cliente.app)


def test_criar_grupo_gera_slug(api):
    logar(api)
    r = _criar(api, descricao="Shows de jazz")
    assert r.status_code == 201
    assert r.json() == {"slug": "jazz-em-natal", "nome": "Jazz em Natal", "descricao": "Shows de jazz",
                        "curador": "Fulana", "n_perfis": 0, "n_seguidores": 0}


def test_slug_repetido_ganha_sufixo_e_nao_muda_ao_renomear(api):
    logar(api)
    _criar(api)
    assert _criar(api).json()["slug"] == "jazz-em-natal-2"
    r = api.cliente.patch("/api/grupos/jazz-em-natal", json={"nome": "Jazz no RN"})
    assert r.status_code == 200 and r.json()["slug"] == "jazz-em-natal" and r.json()["nome"] == "Jazz no RN"


def test_nome_vazio_da_422(api):
    logar(api)
    assert _criar(api, nome="   ").status_code == 422


def test_limite_de_grupos(api):
    logar(api)
    for i in range(10):
        assert _criar(api, nome=f"G{i}").status_code == 201
    r = _criar(api, nome="G10")
    assert r.status_code == 422 and "10" in r.json()["detail"]


def test_listar_meus_e_seguidos(api):
    logar(api, "dona@x.com", "Dona")
    _criar(api, nome="Meu")
    outro = _outro_cliente(api)
    logar(api, "outra@x.com", "Outra", cliente=outro)
    _criar(api, nome="Dela", cliente=outro)
    assert api.cliente.post("/api/grupos/dela/seguir").status_code == 204
    r = api.cliente.get("/api/grupos").json()
    assert [g["slug"] for g in r["meus"]] == ["meu"]
    assert [g["slug"] for g in r["seguidos"]] == ["dela"]


def test_so_o_dono_edita_e_apaga(api):
    logar(api, "dona@x.com", "Dona")
    _criar(api)
    outro = _outro_cliente(api)
    logar(api, "outra@x.com", "Outra", cliente=outro)
    assert outro.patch("/api/grupos/jazz-em-natal", json={"nome": "X"}).status_code == 403
    assert outro.delete("/api/grupos/jazz-em-natal").status_code == 403
    anonimo = _outro_cliente(api)
    assert anonimo.patch("/api/grupos/jazz-em-natal", json={"nome": "X"}).status_code == 401


def test_pagina_publica_sem_sessao_nao_expoe_email(api):
    logar(api, "dona.secreta@x.com", "Dona")
    _criar(api)
    anonimo = _outro_cliente(api)
    r = anonimo.get("/api/grupos/jazz-em-natal")
    assert r.status_code == 200
    corpo = r.json()
    assert (corpo["sou_dono"], corpo["sigo"], corpo["curador"]) == (False, False, "Dona")
    assert corpo["perfis"] == [] and corpo["eventos"] == []
    assert "dona.secreta" not in json.dumps(corpo)
    assert api.cliente.get("/api/grupos/jazz-em-natal").json()["sou_dono"] is True


def test_seguir_e_deixar_de_seguir(api):
    logar(api, "dona@x.com", "Dona")
    _criar(api)
    fa = _outro_cliente(api)
    logar(api, "fa@x.com", "Fã", cliente=fa)
    assert fa.post("/api/grupos/jazz-em-natal/seguir").status_code == 204
    assert fa.post("/api/grupos/jazz-em-natal/seguir").status_code == 204
    g = fa.get("/api/grupos/jazz-em-natal").json()
    assert g["sigo"] is True and g["n_seguidores"] == 1
    assert fa.delete("/api/grupos/jazz-em-natal/seguir").status_code == 204
    assert fa.get("/api/grupos/jazz-em-natal").json()["sigo"] is False


def test_dono_nao_segue_o_proprio(api):
    logar(api)
    _criar(api)
    assert api.cliente.post("/api/grupos/jazz-em-natal/seguir").status_code == 422


def test_seguir_sem_sessao_da_401(api):
    logar(api)
    _criar(api)
    assert _outro_cliente(api).post("/api/grupos/jazz-em-natal/seguir").status_code == 401


def test_slug_inexistente_da_404(api):
    assert api.cliente.get("/api/grupos/nao-existe").status_code == 404


def test_apagar_grupo(api):
    logar(api)
    _criar(api)
    assert api.cliente.delete("/api/grupos/jazz-em-natal").status_code == 204
    assert api.cliente.get("/api/grupos").json()["meus"] == []
