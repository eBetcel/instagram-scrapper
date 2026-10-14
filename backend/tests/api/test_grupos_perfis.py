from datetime import UTC, datetime

from apoio import logar
from fastapi.testclient import TestClient
from sqlalchemy import select

from agenda.models import Job, Perfil


def _grupo(api, nome="Jazz", cliente=None):
    return (cliente or api.cliente).post("/api/grupos", json={"nome": nome}).json()["slug"]


def _add(api, slug, username, cliente=None):
    return (cliente or api.cliente).post(f"/api/grupos/{slug}/perfis", json={"username": username})


def _jobs(api):
    with api.fabrica() as s:
        return [(j.tipo, j.chave) for j in s.scalars(select(Job))]


def test_adicionar_normaliza_e_enfileira_coleta(api):
    logar(api)
    slug = _grupo(api)
    r = _add(api, slug, "@CasaX")
    assert r.status_code == 201 and r.json() == {"username": "casax", "status": "coletando"}
    with api.fabrica() as s:
        pid = s.scalar(select(Perfil.id).where(Perfil.username == "casax"))
    assert _jobs(api) == [("coletar_perfil", f"coletar:{pid}")]
    assert api.cliente.get(f"/api/grupos/{slug}").json()["perfis"] == [{"username": "casax", "status": "coletando"}]


def test_adicionar_de_novo_nao_duplica(api):
    logar(api)
    slug = _grupo(api)
    _add(api, slug, "casax")
    r = _add(api, slug, "casax")
    assert r.status_code == 200
    assert len(_jobs(api)) == 1
    assert api.cliente.get(f"/api/grupos/{slug}").json()["n_perfis"] == 1


def test_perfil_ja_coletado_nao_enfileira(api):
    with api.fabrica() as s:
        s.add(Perfil(username="velho", ultima_coleta_em=datetime.now(UTC)))
        s.commit()
    logar(api)
    r = _add(api, _grupo(api), "velho")
    assert r.status_code == 201 and r.json()["status"] == "ativo"
    assert _jobs(api) == []


def test_perfil_privado_aparece_sinalizado(api):
    with api.fabrica() as s:
        s.add(Perfil(username="fechado", status="privado"))
        s.commit()
    logar(api)
    assert _add(api, _grupo(api), "fechado").json()["status"] == "privado"


def test_username_invalido_da_422(api):
    logar(api)
    assert _add(api, _grupo(api), "nome inválido!").status_code == 422


def test_limite_de_perfis_distintos_somando_grupos(api):
    logar(api)
    a, b = _grupo(api, "A"), _grupo(api, "B")
    for i in range(20):
        assert _add(api, a, f"perfil{i}").status_code == 201
    for i in range(10, 30):  # 10 repetidos de A não contam de novo
        assert _add(api, b, f"perfil{i}").status_code == 201
    r = _add(api, b, "perfil30")
    assert r.status_code == 422 and "30" in r.json()["detail"]
    assert _add(api, a, "perfil25").status_code == 201  # já é dela: não estoura


def test_outro_usuario_nao_mexe_nos_perfis(api):
    logar(api, "dona@x.com", "Dona")
    slug = _grupo(api)
    _add(api, slug, "casax")
    outro = TestClient(api.cliente.app)
    logar(api, "outra@x.com", "Outra", cliente=outro)
    assert _add(api, slug, "casay", cliente=outro).status_code == 403
    assert outro.delete(f"/api/grupos/{slug}/perfis/casax").status_code == 403
    anonimo = TestClient(api.cliente.app)
    assert _add(api, slug, "casay", cliente=anonimo).status_code == 401


def test_remover(api):
    logar(api)
    slug = _grupo(api)
    _add(api, slug, "casax")
    assert api.cliente.delete(f"/api/grupos/{slug}/perfis/casax").status_code == 204
    assert api.cliente.get(f"/api/grupos/{slug}").json()["perfis"] == []
    assert api.cliente.delete(f"/api/grupos/{slug}/perfis/casax").status_code == 404
