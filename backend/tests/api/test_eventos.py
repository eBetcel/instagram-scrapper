from datetime import UTC, datetime, time, timedelta

from apoio import grupo_com, logar, semear
from fastapi.testclient import TestClient

from agenda.extracao.regras import FUSO

HOJE = datetime.now(FUSO).date()


def _dia(d=0, h=20):
    return datetime.combine(HOJE + timedelta(days=d), time(h), tzinfo=FUSO)


def _titulos(r):
    return [e["titulo"] for e in r.json()["eventos"]]


def test_agenda_do_dono_e_do_seguidor(api):
    logar(api, "dona@x.com", "Dona")
    semear(api, "casax", "Show X", _dia(1))
    slug = grupo_com(api, "Jazz", "casax")
    assert _titulos(api.cliente.get("/api/agenda")) == ["Show X"]
    fa = TestClient(api.cliente.app)
    logar(api, "fa@x.com", "Fã", cliente=fa)
    assert _titulos(fa.get("/api/agenda")) == []
    fa.post(f"/api/grupos/{slug}/seguir")
    assert _titulos(fa.get("/api/agenda")) == ["Show X"]


def test_evento_de_perfil_fora_dos_grupos_nao_aparece(api):
    logar(api)
    semear(api, "casax", "Meu", _dia(1))
    semear(api, "outra_casa", "Alheio", _dia(1))
    grupo_com(api, "G", "casax")
    assert _titulos(api.cliente.get("/api/agenda")) == ["Meu"]


def test_agenda_padrao_hoje_ate_mais_7_e_intervalo_explicito(api):
    logar(api)
    semear(api, "casax", "Dia 7", _dia(7))
    semear(api, "casax", "Dia 8", _dia(8))
    semear(api, "casax", "Ontem", _dia(-1))
    grupo_com(api, "G", "casax")
    assert _titulos(api.cliente.get("/api/agenda")) == ["Dia 7"]
    de, ate = (HOJE - timedelta(days=1)).isoformat(), (HOJE + timedelta(days=8)).isoformat()
    assert _titulos(api.cliente.get(f"/api/agenda?de={de}&ate={ate}")) == ["Ontem", "Dia 7", "Dia 8"]


def test_filtros_de_grupo_categoria_e_gratuito(api):
    logar(api)
    semear(api, "casax", "Pago", _dia(1, 21), categoria="show", preco_min=30, preco_max=30)
    semear(api, "casax", "Grátis", _dia(1, 18), categoria="festa", gratuito=True)
    semear(api, "casay", "Zero", _dia(2), categoria="show", preco_max=0)
    a = grupo_com(api, "A", "casax")
    grupo_com(api, "B", "casay")
    assert _titulos(api.cliente.get(f"/api/agenda?grupo={a}")) == ["Grátis", "Pago"]
    assert _titulos(api.cliente.get("/api/agenda?categoria=show")) == ["Pago", "Zero"]
    assert _titulos(api.cliente.get("/api/agenda?gratuito=true")) == ["Grátis", "Zero"]


def test_agenda_sem_sessao_da_401(api):
    assert api.cliente.get("/api/agenda").status_code == 401


def test_alterado_so_com_atualizacao_recente(api):
    logar(api)
    a, _ = semear(api, "casax", "Recente", _dia(1))
    semear(api, "casax", "", None, evento_id=a, decisao="atualizacao",
           fonte_em=datetime.now(UTC) - timedelta(days=2))
    b, _ = semear(api, "casax", "Antiga", _dia(2))
    semear(api, "casax", "", None, evento_id=b, decisao="atualizacao",
           fonte_em=datetime.now(UTC) - timedelta(days=10))
    c, _ = semear(api, "casax", "Só duplicado", _dia(3))
    semear(api, "casax", "", None, evento_id=c, decisao="duplicado")
    grupo_com(api, "G", "casax")
    alterado = {e["titulo"]: e["alterado"] for e in api.cliente.get("/api/agenda").json()["eventos"]}
    assert alterado == {"Recente": True, "Antiga": False, "Só duplicado": False}


def test_imagem_do_post_mais_antigo(api):
    logar(api)
    ev, sc_antigo = semear(api, "casax", "Show", _dia(1), publicado_em=datetime.now(UTC) - timedelta(days=5))
    semear(api, "casay", "", None, evento_id=ev, decisao="duplicado")
    semear(api, "casax", "Sem flyer", _dia(2), imagens=[])
    grupo_com(api, "G", "casax")
    imagens = {e["titulo"]: e["imagem"] for e in api.cliente.get("/api/agenda").json()["eventos"]}
    assert imagens == {"Show": f"/api/posts/{sc_antigo}/imagens/0", "Sem flyer": None}


def test_formato_do_evento(api):
    logar(api)
    semear(api, "casax", "Show", _dia(1), local_nome="Casa X", cidade="Natal", festival="F",
           artistas=["Banda"], hora_definida=False)
    grupo_com(api, "G", "casax")
    [e] = api.cliente.get("/api/agenda").json()["eventos"]
    assert set(e) == {"id", "titulo", "inicio", "hora_definida", "fim", "local_nome", "cidade",
                      "categoria", "preco_texto", "gratuito", "preco_min", "preco_max",
                      "link_ingresso", "status", "festival", "artistas", "alterado", "imagem"}
    assert (e["local_nome"], e["hora_definida"], e["artistas"]) == ("Casa X", False, ["Banda"])


def test_detalhe_publico_com_fontes_e_revisoes(api):
    from agenda.models import RevisaoEvento

    ev, sc = semear(api, "casax", "Show", _dia(1), descricao="Desc", endereco="Rua A")
    with api.fabrica() as s:
        s.add(RevisaoEvento(evento_id=ev, campo="preco_min", valor_anterior="10", valor_novo="20", motivo="m"))
        s.commit()
    r = api.cliente.get(f"/api/eventos/{ev}")
    assert r.status_code == 200
    d = r.json()
    assert (d["descricao"], d["endereco"]) == ("Desc", "Rua A")
    [f] = d["fontes"]
    assert (f["username"], f["shortcode"], f["url_instagram"], f["decisao"]) == (
        "casax", sc, f"https://www.instagram.com/p/{sc}/", "novo")
    [rev] = d["revisoes"]
    assert (rev["campo"], rev["valor_anterior"], rev["valor_novo"]) == ("preco_min", "10", "20")
    assert api.cliente.get("/api/eventos/999999").status_code == 404


def test_grupo_publico_lista_proximos_30_dias(api):
    logar(api)
    semear(api, "casax", "Logo", _dia(5))
    semear(api, "casax", "Longe", _dia(40))
    slug = grupo_com(api, "G", "casax")
    anonimo = TestClient(api.cliente.app)
    assert [e["titulo"] for e in anonimo.get(f"/api/grupos/{slug}").json()["eventos"]] == ["Logo"]


def test_imagem_do_storage(api):
    api.storage.salvar("posts/X/0.jpg", b"\xff\xd8jpeg", "image/jpeg")
    r = api.cliente.get("/api/posts/X/imagens/0")
    assert r.status_code == 200 and r.content == b"\xff\xd8jpeg"
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["cache-control"] == "public, max-age=86400"
    assert api.cliente.get("/api/posts/X/imagens/1").status_code == 404
