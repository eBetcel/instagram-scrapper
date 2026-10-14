import json
from datetime import date, datetime
from pathlib import Path

from agenda.avaliacao.golden import (
    avaliar_extracao,
    avaliar_reconciliacao,
    carregar_casos,
)
from agenda.extracao.extrator import Resultado, Uso
from agenda.extracao.schema import Confianca, EventoExtraido, ExtracaoPost
from agenda.reconciliacao.decisao import Decisao, FakeReconciliador

GOLDEN = Path(__file__).parent.parent / "fixtures" / "golden"


def _ev(**kw) -> EventoExtraido:
    base = dict(
        titulo=None, descricao=None, data_inicio=None, hora_inicio=None, data_fim=None,
        hora_fim=None, local_nome=None, endereco=None, cidade=None, categoria="outro",
        preco_texto=None, gratuito=None, preco_min=None, preco_max=None, link_ingresso=None,
        artistas=[], festival=None, status_indicado=None,
        confianca=Confianca(data_inicio=1, hora_inicio=1, local_nome=1),
    )
    return EventoExtraido(**{**base, **kw})


class ExtratorPorUsername:
    def __init__(self, respostas):
        self.respostas = respostas

    def extrair(self, legenda, imagens, username, publicado_em):
        return Resultado(self.respostas[legenda.split()[0]], Uso(10, 5, __import__("decimal").Decimal("0.5"), "fake"))


def test_carregar_casos_le_esperado_json():
    casos = carregar_casos(GOLDEN)
    assert [c.nome for c in casos] == ["c1_show", "c2_multi", "c3_recon"]
    c1 = casos[0]
    assert c1.username == "casax"
    assert c1.publicado_em == datetime.fromisoformat("2026-10-06T12:00:00-03:00")
    assert c1.legenda.startswith("Rock")
    assert c1.imagens == []
    assert c1.eventos[0]["data_inicio"] == date(2026, 10, 10).isoformat()
    assert casos[2].reconciliacao["decisao_esperada"] == "ATUALIZACAO"
    assert casos[0].reconciliacao is None


def test_relatorio_extracao_calcula_acuracia_por_campo():
    casos = [c for c in carregar_casos(GOLDEN) if c.nome == "c1_show"]
    # titulo certo, categoria errada; demais campos pontuados erram (None)
    ext = ExtratorPorUsername({"Rock": ExtracaoPost(eventos=[
        _ev(titulo="Rock na Casa X", data_inicio=date(2026, 10, 10), categoria="festa")
    ])})
    rel = avaliar_extracao(casos, ext)
    assert rel.acuracia["titulo"] == 1.0
    assert rel.acuracia["data_inicio"] == 1.0
    assert rel.acuracia["categoria"] == 0.0
    assert rel.acuracia["cidade"] == 0.0
    assert rel.eventos_esperados == 1 and rel.eventos_extraidos == 1
    assert rel.uso_total.custo > 0
    assert "titulo" in rel.formatar()


def test_relatorio_extracao_um_campo_certo_um_errado_da_meia():
    casos = [c for c in carregar_casos(GOLDEN) if c.nome == "c2_multi"]
    ext = ExtratorPorUsername({"Programação:": ExtracaoPost(eventos=[
        _ev(titulo="Jazz", data_inicio=date(2026, 10, 11), categoria="show"),
        _ev(titulo="Samba", data_inicio=date(2026, 10, 12), categoria="festa"),
    ])})
    rel = avaliar_extracao(casos, ext)
    assert rel.acuracia["categoria"] == 0.5
    assert rel.acuracia["titulo"] == 1.0


def test_relatorio_reconciliacao_conta_acertos_de_decisao():
    casos = carregar_casos(GOLDEN)
    certo = Decisao(decisao="ATUALIZACAO", evento_id=7, mudancas=["inicio"], motivo="x")
    rel = avaliar_reconciliacao(casos, FakeReconciliador([certo]))
    assert rel.total == 1 and rel.acertos_decisao == 1 and rel.acertos_evento_id == 1
    errado = Decisao(decisao="NOVO", evento_id=None, mudancas=[], motivo="x")
    rel = avaliar_reconciliacao(casos, FakeReconciliador([errado]))
    assert rel.acertos_decisao == 0 and rel.acertos_evento_id == 0


def test_cli_avaliar_rejeita_etapa_invalida():
    from typer.testing import CliRunner

    from agenda.cli import app

    r = CliRunner().invoke(app, ["avaliar", "--etapa", "x", "--golden", str(GOLDEN)])
    assert r.exit_code == 1


def test_reconciliacao_novo_esperado_ignora_evento_id(tmp_path):
    import json

    caso = tmp_path / "novo"
    caso.mkdir()
    (caso / "esperado.json").write_text(json.dumps({
        "username": "casa", "publicado_em": "2026-10-06T12:00:00-03:00",
        "eventos": [{"titulo": "Show", "data_inicio": "2026-10-10"}],
        "reconciliacao": {
            "candidatos": [{"id": 3, "titulo": "Outro", "inicio": "2026-10-10T21:00:00-03:00"}],
            "evento": 0, "decisao_esperada": "NOVO", "evento_id_esperado": None,
        },
    }))
    casos = carregar_casos(tmp_path)
    # NOVO com evento_id preenchido: aplicar ignora o id (R22), então está certo.
    novo_com_id = Decisao(decisao="NOVO", evento_id=3, mudancas=[], motivo="x")
    rel = avaliar_reconciliacao(casos, FakeReconciliador([novo_com_id]))
    assert rel.total == 1 and rel.acertos_decisao == 1
    assert rel.total_evento_id == 0 and rel.acertos_evento_id == 0
    assert rel.erros == []
    assert "evento_id  0/0" in rel.formatar()


def test_relatorio_extracao_pontua_atracoes_agrupadas_no_festival():
    casos = [c for c in carregar_casos(GOLDEN) if c.nome == "c1_show"]
    # Duas atrações do mesmo festival no dia esperado viram um evento "Rock na Casa X".
    ext = ExtratorPorUsername({"Rock": ExtracaoPost(eventos=[
        _ev(titulo="Banda A", data_inicio=date(2026, 10, 10), festival="Rock na Casa X"),
        _ev(titulo="Banda B", data_inicio=date(2026, 10, 10), festival="Rock na Casa X"),
    ])})
    rel = avaliar_extracao(casos, ext)
    assert rel.eventos_extraidos == 1
    assert rel.acuracia["titulo"] == 1.0


class Registrador:
    def __init__(self):
        self.chamadas = []

    def decidir(self, e, candidatos, post, *, exigir_candidato=False):
        self.chamadas.append(([c.id for c in candidatos], exigir_candidato))
        return Decisao(decisao="DUPLICADO", evento_id=candidatos[0].id, mudancas=[], motivo="x"), None


def test_reconciliacao_do_golden_segue_o_par_forte_como_o_pipeline(tmp_path):
    caso = tmp_path / "festival"
    caso.mkdir()
    (caso / "legenda.txt").write_text("Siba no festival")
    (caso / "esperado.json").write_text(json.dumps({
        "username": "dosol", "publicado_em": "2026-10-13T12:00:00-03:00",
        "eventos": [{"titulo": "Festival DoSol 2026", "data_inicio": "2026-11-28",
                     "festival": "Festival DoSol 2026"}],
        "reconciliacao": {
            "candidatos": [
                {"id": 1, "titulo": "Festival DoSol 2026", "inicio": "2026-11-27T19:00:00-03:00"},
                {"id": 2, "titulo": "Festival do Sol", "inicio": "2026-11-28T16:00:00-03:00",
                 "festival": "Festival DoSol 2026"},
            ],
            "evento": 0, "decisao_esperada": "DUPLICADO", "evento_id_esperado": 2,
        },
    }))
    reg = Registrador()
    rel = avaliar_reconciliacao(carregar_casos(tmp_path), reg)
    assert reg.chamadas == [([2], True)]
    assert rel.acertos_decisao == 1
