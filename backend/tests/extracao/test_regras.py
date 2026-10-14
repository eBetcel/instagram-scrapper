from datetime import date, datetime, time, timedelta, timezone

from agenda.extracao.regras import (
    FUSO,
    agrupar_festivais,
    filtrar_validos,
    instrucoes_datas,
    normalizar_preco,
    para_fim,
    para_inicio,
)
from agenda.extracao.schema import Confianca, EventoExtraido, ExtracaoPost

AGORA = datetime(2026, 10, 13, 15, 0, tzinfo=FUSO)


def ev(**kw) -> EventoExtraido:
    base = dict(
        titulo="Show", descricao=None, data_inicio=date(2026, 10, 20),
        hora_inicio=None, data_fim=None, hora_fim=None, local_nome=None,
        endereco=None, cidade=None, categoria="show", preco_texto=None,
        gratuito=None, preco_min=None, preco_max=None, link_ingresso=None,
        artistas=[], festival=None, status_indicado=None,
        confianca=Confianca(data_inicio=1.0, hora_inicio=1.0, local_nome=1.0),
    )
    base.update(kw)
    return EventoExtraido(**base)


def test_filtra_sem_titulo():
    assert filtrar_validos([ev(titulo=None)], AGORA) == []


def test_filtra_titulo_em_branco():
    assert filtrar_validos([ev(titulo="   ")], AGORA) == []


def test_filtra_sem_data():
    assert filtrar_validos([ev(data_inicio=None)], AGORA) == []


def test_filtra_data_passada_e_mantem_hoje():
    ontem = ev(data_inicio=date(2026, 10, 12))
    hoje = ev(data_inicio=date(2026, 10, 13))
    assert filtrar_validos([ontem, hoje], AGORA) == [hoje]


def test_hoje_usa_fuso_de_sao_paulo():
    # 01:00 UTC de 14/10 ainda e 13/10 em Sao Paulo
    agora = datetime(2026, 10, 14, 1, 0, tzinfo=timezone.utc)
    e = ev(data_inicio=date(2026, 10, 13))
    assert filtrar_validos([e], agora) == [e]


def test_exposicao_em_andamento_e_mantida():
    e = ev(data_inicio=date(2026, 9, 1), data_fim=date(2026, 11, 1))
    assert filtrar_validos([e], AGORA) == [e]


def test_exposicao_encerrada_e_descartada():
    e = ev(data_inicio=date(2026, 9, 1), data_fim=date(2026, 10, 1))
    assert filtrar_validos([e], AGORA) == []


def test_post_com_varios_eventos_mantem_todos():
    eventos = [ev(titulo=f"E{i}") for i in range(10)]
    assert len(filtrar_validos(eventos, AGORA)) == 10


def test_sem_hora_marca_hora_definida_false():
    dt, definida = para_inicio(ev())
    assert definida is False
    assert dt == datetime(2026, 10, 20, 0, 0, tzinfo=FUSO)


def test_com_hora_marca_hora_definida_true():
    dt, definida = para_inicio(ev(hora_inicio=time(21, 30)))
    assert definida is True
    assert dt == datetime(2026, 10, 20, 21, 30, tzinfo=FUSO)
    assert dt.utcoffset() == timedelta(hours=-3)


def test_hora_apos_meia_noite_mantem_o_dia_do_evento():
    dt, definida = para_inicio(ev(data_inicio=date(2026, 10, 17), hora_inicio=time(1, 0)))
    assert definida is True
    assert dt.date() == date(2026, 10, 17)


def test_para_fim_none_sem_fim():
    assert para_fim(ev(hora_inicio=time(20, 0))) is None


def test_para_fim_hora_apos_meia_noite_vira_dia_seguinte():
    e = ev(hora_inicio=time(22, 0), hora_fim=time(2, 0))
    assert para_fim(e) == datetime(2026, 10, 21, 2, 0, tzinfo=FUSO)


def test_para_fim_hora_fim_mesmo_dia():
    e = ev(hora_inicio=time(20, 0), hora_fim=time(23, 0))
    assert para_fim(e) == datetime(2026, 10, 20, 23, 0, tzinfo=FUSO)


def test_para_fim_data_fim_sem_hora_vai_ate_2359():
    e = ev(data_fim=date(2026, 11, 1))
    assert para_fim(e) == datetime(2026, 11, 1, 23, 59, tzinfo=FUSO)


def test_para_fim_data_fim_e_hora_fim():
    e = ev(data_fim=date(2026, 11, 1), hora_fim=time(18, 0))
    assert para_fim(e) == datetime(2026, 11, 1, 18, 0, tzinfo=FUSO)


def test_gratuito_zera_precos():
    e = ev(gratuito=True, preco_min=10.0, preco_max=20.0)
    r = normalizar_preco(e)
    assert r.preco_min == 0 and r.preco_max == 0
    assert e.preco_min == 10.0


def test_preco_min_maior_que_max_e_trocado():
    r = normalizar_preco(ev(preco_min=40.0, preco_max=30.0))
    assert (r.preco_min, r.preco_max) == (30.0, 40.0)


def test_instrucoes_datas_contem_ano_seguinte_para_dezembro():
    txt = instrucoes_datas(datetime(2026, 12, 20, 12, 0, tzinfo=FUSO))
    assert "2026-12-20" in txt
    assert "domingo" in txt
    assert "assuma o ano seguinte" in txt


def test_instrucoes_datas_usa_fuso_e_dia_da_semana():
    txt = instrucoes_datas(datetime(2026, 10, 11, 1, 0, tzinfo=timezone.utc))
    assert "2026-10-10" in txt
    assert "sábado" in txt


def test_schema_estrito_para_openai():
    schema = ExtracaoPost.model_json_schema()
    defs = schema["$defs"]
    for nome in ("EventoExtraido", "Confianca"):
        d = defs[nome]
        assert set(d["required"]) == set(d["properties"])
        assert d["additionalProperties"] is False


def test_hora_com_fuso_vira_hora_local_ingenua():
    # O modelo às vezes devolve "17:00:00Z" ou "19:00:00-03:00" para o "17H" do flyer.
    e = EventoExtraido.model_validate(
        {**ev().model_dump(mode="json"), "hora_inicio": "17:00:00Z", "hora_fim": "23:00:00-03:00"}
    )
    assert e.hora_inicio == time(17, 0) and e.hora_inicio.tzinfo is None
    assert e.hora_fim == time(23, 0) and e.hora_fim.tzinfo is None


# --- agrupar_festivais ---------------------------------------------------------

MADA = "Festival MADA 2026"
D16, D17 = date(2026, 10, 16), date(2026, 10, 17)


def test_agrupa_atracoes_do_festival_por_dia():
    eventos = [
        ev(titulo="Show do Zeca", data_inicio=D16, festival=MADA, artistas=["Zeca Pagodinho"]),
        ev(titulo="Show do Emicida", data_inicio=D17, festival=MADA, artistas=["Emicida"]),
        ev(titulo="Baile com Belisa", data_inicio=D16, festival=MADA, artistas=["Belisa", "zeca pagodinho"]),
    ]
    dia16, dia17 = agrupar_festivais(eventos)
    assert (dia16.titulo, dia16.data_inicio, dia16.festival, dia16.categoria) == (MADA, D16, MADA, "festival")
    assert dia16.artistas == ["Zeca Pagodinho", "Belisa"]
    assert (dia17.titulo, dia17.data_inicio, dia17.artistas) == (MADA, D17, ["Emicida"])
    assert dia16.data_fim is None


def test_agrupa_local_igual_mantem_e_divergente_vira_null():
    iguais = agrupar_festivais([
        ev(data_inicio=D16, festival=MADA, local_nome="Arena das Dunas", cidade="Natal"),
        ev(data_inicio=D16, festival=MADA, local_nome="arena das dunas", cidade=None),
    ])
    assert (iguais[0].local_nome, iguais[0].cidade) == ("Arena das Dunas", "Natal")
    divergentes = agrupar_festivais([
        ev(data_inicio=D16, festival=MADA, local_nome="Palco A", cidade="Natal"),
        ev(data_inicio=D16, festival=MADA, local_nome="Palco B", cidade="Macaíba"),
    ])
    assert (divergentes[0].local_nome, divergentes[0].cidade) == (None, None)


def test_agrupa_hora_mais_cedo_e_descricao_por_atracao():
    [g] = agrupar_festivais([
        ev(titulo="Show do Siba", data_inicio=D16, hora_inicio=time(21, 0), festival=MADA, local_nome="Palco Rua Chile"),
        ev(titulo="Vanguart", data_inicio=D16, hora_inicio=time(16, 0), hora_fim=time(17, 0), festival=MADA),
    ])
    assert (g.hora_inicio, g.hora_fim) == (time(16, 0), time(17, 0))
    assert "Show do Siba" in g.descricao and "Palco Rua Chile" in g.descricao and "Vanguart" in g.descricao


def test_agrupa_status_esgotado_se_algum_e_cancelado_so_se_todos():
    [g] = agrupar_festivais([
        ev(data_inicio=D16, festival=MADA, status_indicado="esgotado"),
        ev(data_inicio=D16, festival=MADA, status_indicado="cancelado"),
    ])
    assert g.status_indicado == "esgotado"
    [g] = agrupar_festivais([
        ev(data_inicio=D16, festival=MADA, status_indicado="cancelado"),
        ev(data_inicio=D16, festival=MADA),
    ])
    assert g.status_indicado is None
    [g] = agrupar_festivais([ev(data_inicio=D16, festival=MADA, status_indicado="adiado")] * 2)
    assert g.status_indicado == "adiado"


def test_agrupa_preco_e_confianca():
    [g] = agrupar_festivais([
        ev(data_inicio=D16, festival=MADA, preco_min=50.0, preco_max=80.0, gratuito=False,
           confianca=Confianca(data_inicio=0.9, hora_inicio=0.2, local_nome=1.0)),
        ev(data_inicio=D16, festival=MADA, preco_min=30.0, preco_max=60.0, link_ingresso="https://x",
           confianca=Confianca(data_inicio=0.5, hora_inicio=0.8, local_nome=0.7)),
    ])
    assert (g.preco_min, g.preco_max, g.gratuito, g.link_ingresso) == (30.0, 80.0, False, "https://x")
    assert g.confianca == Confianca(data_inicio=0.5, hora_inicio=0.2, local_nome=0.7)


def test_evento_sem_festival_passa_intacto():
    avulso = ev(titulo="Jáder (PE)", data_inicio=D16)
    atracao = ev(titulo="Show do Zeca", data_inicio=D16, festival=MADA)
    resultado = agrupar_festivais([avulso, atracao])
    assert resultado[0] == avulso
    assert resultado[1].titulo == MADA


def test_nome_do_festival_normalizado_agrupa():
    assert len(agrupar_festivais([
        ev(data_inicio=D16, festival="Festival MADA 2026"),
        ev(data_inicio=D16, festival="festival mada 2026"),
    ])) == 1
