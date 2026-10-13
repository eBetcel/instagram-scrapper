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
        artistas=[], status_indicado=None,
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
