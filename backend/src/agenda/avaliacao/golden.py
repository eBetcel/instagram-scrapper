"""Golden set: carregamento de casos anotados e métricas de extração e reconciliação.

Não usa banco: `Evento`, `Post` e `Perfil` são criados apenas em memória (transientes)
para chamar `Reconciliador.decidir`. Formato dos casos em `backend/golden/README.md`.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from agenda.extracao.extrator import Extrator, Uso
from agenda.extracao.schema import EventoExtraido
from agenda.models import Evento, Perfil, Post
from agenda.reconciliacao.candidatos import normalizar_artistas
from agenda.reconciliacao.decisao import Reconciliador

LIMIAR_TITULO = 0.8
CAMPOS = ("titulo", "data_inicio", "hora_inicio", "cidade", "categoria", "artistas", "preco_min", "preco_max")


@dataclass
class CasoGolden:
    nome: str
    username: str
    publicado_em: datetime
    legenda: str
    imagens: list[Path]
    eventos: list[dict[str, Any]]
    reconciliacao: dict[str, Any] | None = None


def carregar_casos(diretorio: Path) -> list[CasoGolden]:
    casos = []
    for pasta in sorted(p for p in Path(diretorio).iterdir() if (p / "esperado.json").is_file()):
        esperado = json.loads((pasta / "esperado.json").read_text(encoding="utf-8"))
        legenda_arq = pasta / "legenda.txt"
        casos.append(
            CasoGolden(
                nome=pasta.name,
                username=esperado["username"],
                publicado_em=datetime.fromisoformat(esperado["publicado_em"]),
                legenda=legenda_arq.read_text(encoding="utf-8") if legenda_arq.is_file() else "",
                imagens=sorted(pasta.glob("imagem*.jpg")),
                eventos=esperado.get("eventos", []),
                reconciliacao=esperado.get("reconciliacao"),
            )
        )
    return casos


def _norm(texto: str | None) -> str:
    nomes = normalizar_artistas([texto or ""])
    return nomes[0] if nomes else ""


def similaridade_titulo(a: str | None, b: str | None) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _f1(esperado: list[str], obtido: list[str]) -> float:
    e, o = set(normalizar_artistas(esperado)), set(normalizar_artistas(obtido))
    if not e and not o:
        return 1.0
    acertos = len(e & o)
    if acertos == 0:
        return 0.0
    p, r = acertos / len(o), acertos / len(e)
    return 2 * p * r / (p + r)


def _data(v: Any) -> date | None:
    return v if v is None or isinstance(v, date) else date.fromisoformat(v)


def _hora(v: Any) -> time | None:
    return v if v is None or isinstance(v, time) else time.fromisoformat(v)


def _preco(v: Any) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def _pontuar(campo: str, esperado: Any, obtido: Any) -> float:
    if campo == "titulo":
        return float(similaridade_titulo(esperado, obtido) >= LIMIAR_TITULO)
    if campo == "artistas":
        return _f1(esperado, obtido)
    conv = {"data_inicio": _data, "hora_inicio": _hora, "preco_min": _preco, "preco_max": _preco}.get(
        campo, lambda v: v
    )
    return float(conv(esperado) == conv(obtido))


def _parear(esperados: list[dict], extraidos: list[EventoExtraido]) -> list[EventoExtraido | None]:
    livres = list(extraidos)
    pares: list[EventoExtraido | None] = []
    for esp in esperados:
        mesma_data = [x for x in livres if x.data_inicio is not None and x.data_inicio == _data(esp.get("data_inicio"))]
        pool = mesma_data or livres
        if not pool:
            pares.append(None)
            continue
        melhor = max(pool, key=lambda x: similaridade_titulo(esp.get("titulo"), x.titulo))
        livres.remove(melhor)
        pares.append(melhor)
    return pares


@dataclass
class RelatorioExtracao:
    acuracia: dict[str, float] = field(default_factory=dict)
    amostras: dict[str, int] = field(default_factory=dict)
    eventos_esperados: int = 0
    eventos_extraidos: int = 0
    por_caso: list[tuple[str, int, int]] = field(default_factory=list)
    uso_total: Uso = field(default_factory=lambda: Uso(0, 0, Decimal(0), "-"))

    def formatar(self) -> str:
        linhas = ["Extração — acurácia por campo"]
        for campo in CAMPOS:
            if campo in self.acuracia:
                linhas.append(f"  {campo:<12} {self.acuracia[campo]:.2%}  (n={self.amostras[campo]})")
        linhas.append(f"Eventos esperados/extraídos: {self.eventos_esperados}/{self.eventos_extraidos}")
        for nome, esp, ext in self.por_caso:
            linhas.append(f"  {nome}: {esp}/{ext}")
        linhas.append(_fmt_uso(self.uso_total))
        return "\n".join(linhas)


def _fmt_uso(u: Uso) -> str:
    return f"Tokens: {u.tokens_entrada} entrada, {u.tokens_saida} saída; custo estimado: US$ {u.custo:.4f}"


def _somar(a: Uso, b: Uso | None) -> Uso:
    if b is None:
        return a
    return Uso(a.tokens_entrada + b.tokens_entrada, a.tokens_saida + b.tokens_saida, a.custo + b.custo, b.modelo)


def avaliar_extracao(casos: list[CasoGolden], extrator: Extrator) -> RelatorioExtracao:
    rel = RelatorioExtracao()
    soma: dict[str, float] = {}
    for caso in casos:
        res = extrator.extrair(
            caso.legenda, [p.read_bytes() for p in caso.imagens], caso.username, caso.publicado_em
        )
        rel.uso_total = _somar(rel.uso_total, res.uso)
        extraidos = res.extracao.eventos
        rel.eventos_esperados += len(caso.eventos)
        rel.eventos_extraidos += len(extraidos)
        rel.por_caso.append((caso.nome, len(caso.eventos), len(extraidos)))
        for esp, obtido in zip(caso.eventos, _parear(caso.eventos, extraidos), strict=True):
            for campo in CAMPOS:
                if campo not in esp:
                    continue
                rel.amostras[campo] = rel.amostras.get(campo, 0) + 1
                if obtido is not None:
                    soma[campo] = soma.get(campo, 0.0) + _pontuar(campo, esp[campo], getattr(obtido, campo))
    rel.acuracia = {c: soma.get(c, 0.0) / n for c, n in rel.amostras.items()}
    return rel


@dataclass
class RelatorioDecisao:
    total: int = 0
    acertos_decisao: int = 0
    acertos_evento_id: int = 0
    total_evento_id: int = 0  # só casos com decisão esperada != NOVO (R22)
    erros: list[str] = field(default_factory=list)
    uso_total: Uso = field(default_factory=lambda: Uso(0, 0, Decimal(0), "-"))

    def formatar(self) -> str:
        t = max(self.total, 1)
        linhas = [
            "Reconciliação",
            f"  decisão    {self.acertos_decisao}/{self.total} ({self.acertos_decisao / t:.2%})",
            f"  evento_id  {self.acertos_evento_id}/{self.total_evento_id} "
            f"({self.acertos_evento_id / max(self.total_evento_id, 1):.2%}; só DUPLICADO/ATUALIZACAO)",
            *[f"  erro: {e}" for e in self.erros],
            _fmt_uso(self.uso_total),
        ]
        return "\n".join(linhas)


_CAMPOS_EVENTO_DT = ("inicio", "fim")


def _evento_transiente(d: dict[str, Any]) -> Evento:
    dados = dict(d)
    for k in _CAMPOS_EVENTO_DT:
        if dados.get(k):
            dados[k] = datetime.fromisoformat(dados[k])
    for k in ("preco_min", "preco_max"):
        if dados.get(k) is not None:
            dados[k] = Decimal(str(dados[k]))
    dados.setdefault("categoria", "outro")
    dados.setdefault("status", "ativo")
    dados.setdefault("hora_definida", True)
    dados.setdefault("artistas", [])
    return Evento(**dados)


def _evento_extraido(d: dict[str, Any]) -> EventoExtraido:
    base: dict[str, Any] = {
        "titulo": None, "descricao": None, "data_inicio": None, "hora_inicio": None,
        "data_fim": None, "hora_fim": None, "local_nome": None, "endereco": None, "cidade": None,
        "categoria": "outro", "preco_texto": None, "gratuito": None, "preco_min": None,
        "preco_max": None, "link_ingresso": None, "artistas": [], "festival": None, "status_indicado": None,
        "confianca": {"data_inicio": 1.0, "hora_inicio": 1.0, "local_nome": 1.0},
    }
    return EventoExtraido.model_validate({**base, **d})


def avaliar_reconciliacao(casos: list[CasoGolden], reconciliador: Reconciliador) -> RelatorioDecisao:
    rel = RelatorioDecisao()
    for caso in casos:
        rec = caso.reconciliacao
        if rec is None:
            continue
        candidatos = [_evento_transiente(c) for c in rec["candidatos"]]
        post = Post(
            shortcode=caso.nome, legenda=caso.legenda, publicado_em=caso.publicado_em,
            perfil=Perfil(username=caso.username),
        )
        evento = _evento_extraido(caso.eventos[rec["evento"]])
        decisao, uso = reconciliador.decidir(evento, candidatos, post)
        rel.uso_total = _somar(rel.uso_total, uso)
        rel.total += 1
        ok_dec = decisao.decisao == rec["decisao_esperada"]
        # NOVO ignora evento_id (R22): só se compara o id quando se espera um candidato.
        ok_id = True
        if rec["decisao_esperada"] != "NOVO":
            ok_id = decisao.evento_id == rec.get("evento_id_esperado")
            rel.total_evento_id += 1
            rel.acertos_evento_id += ok_id
        rel.acertos_decisao += ok_dec
        if not (ok_dec and ok_id):
            rel.erros.append(
                f"{caso.nome}: esperado {rec['decisao_esperada']}/{rec.get('evento_id_esperado')}, "
                f"obtido {decisao.decisao}/{decisao.evento_id}"
            )
    return rel
