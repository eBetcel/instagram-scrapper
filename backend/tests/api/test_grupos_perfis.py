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


def test_adicionar_normaliza_e_cria_perfil_sem_enfileirar(api):
    logar(api)
    slug = _grupo(api)
    r = _add(api, slug, "@CasaX")
    assert r.status_code == 201 and r.json() == {"username": "casax", "status": "coletando"}
    with api.fabrica() as s:
        assert s.scalar(select(Perfil.id).where(Perfil.username == "casax")) is not None
    assert _jobs(api) == []  # a coleta de perfis novos é feita em lote pelo worker
    assert api.cliente.get(f"/api/grupos/{slug}").json()["perfis"] == [{"username": "casax", "status": "coletando"}]


def test_adicionar_de_novo_nao_duplica(api):
    logar(api)
    slug = _grupo(api)
    _add(api, slug, "casax")
    r = _add(api, slug, "casax")
    assert r.status_code == 200
    assert api.cliente.get(f"/api/grupos/{slug}").json()["n_perfis"] == 1


def test_perfil_ja_coletado_aparece_ativo(api):
    with api.fabrica() as s:
        s.add(Perfil(username="velho", ultima_coleta_em=datetime.now(UTC)))
        s.commit()
    logar(api)
    r = _add(api, _grupo(api), "velho")
    assert r.status_code == 201 and r.json()["status"] == "ativo"


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


def _lote(api, slug, usernames, cliente=None):
    return (cliente or api.cliente).post(f"/api/grupos/{slug}/perfis/lote", json={"usernames": usernames})


def test_lote_adiciona_varios_sem_enfileirar(api):
    with api.fabrica() as s:
        s.add(Perfil(username="velho", ultima_coleta_em=datetime.now(UTC)))
        s.commit()
    logar(api)
    slug = _grupo(api)
    r = _lote(api, slug, ["@CasaX", "velho", "casax"])
    assert r.status_code == 200
    assert r.json()["resultados"] == [
        {"username": "casax", "status": "coletando", "erro": None},
        {"username": "velho", "status": "ativo", "erro": None},
        {"username": "casax", "status": "coletando", "erro": None},
    ]
    assert _jobs(api) == []
    assert api.cliente.get(f"/api/grupos/{slug}").json()["n_perfis"] == 2


def test_lote_invalido_nao_derruba_os_validos(api):
    logar(api)
    slug = _grupo(api)
    r = _lote(api, slug, ["casax", "@@inválido!"])
    resultados = r.json()["resultados"]
    assert resultados[0]["erro"] is None
    assert resultados[1]["username"] == "@@inválido!" and resultados[1]["status"] is None
    assert "inválido" in resultados[1]["erro"]
    assert api.cliente.get(f"/api/grupos/{slug}").json()["n_perfis"] == 1


def test_lote_respeita_o_limite_de_perfis(api):
    logar(api)
    slug = _grupo(api)
    limite = 30
    r = _lote(api, slug, [f"perfil{i}" for i in range(limite + 1)])
    erros = [x["erro"] for x in r.json()["resultados"] if x["erro"]]
    assert len(erros) == 1 and str(limite) in erros[0]
    assert api.cliente.get(f"/api/grupos/{slug}").json()["n_perfis"] == limite


def test_lote_so_o_dono(api):
    logar(api)
    slug = _grupo(api)
    outro = TestClient(api.cliente.app)
    logar(api, "outra@exemplo.com", cliente=outro)
    assert _lote(api, slug, ["casax"], cliente=outro).status_code == 403
