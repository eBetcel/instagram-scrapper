# Deduplicação de Eventos e Agrupamento de Festivais — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um evento por (nome parecido, dia); atrações de festival agrupadas no evento do festival por dia; fusão das duplicatas existentes.

**Architecture:** A extração ganha `festival`; a reconciliação agrupa as atrações por `(festival, dia)` antes de buscar candidatos. Uma função pura `mesmo_evento` decide identidade; com par forte o modelo só escolhe DUPLICADO/ATUALIZACAO. `fundir`/`deduplicar` limpam o banco, chamados pelo worker e pela CLI.

**Tech Stack:** Python 3.12, SQLAlchemy 2, Alembic, Postgres 16 (`pg_trgm`), pydantic v2, Typer, pytest + testcontainers.

**Spec:** `docs/superpowers/specs/2026-10-14-deduplicacao-eventos-design.md`

## Global Constraints

- Fuso `America/Sao_Paulo` para "mesmo dia".
- `EventoExtraido` segue compatível com structured outputs estritos: todo campo obrigatório, anulável via `X | None`, sem default.
- `nomes_parecidos`: igualdade normalizada, ou `tokens(a) ⊆ tokens(b)` (ou o inverso), ou `SequenceMatcher` ≥ 0,8 entre os tokens que diferem (`sorted(ta - tb)` × `sorted(tb - ta)`), nunca sobre o texto inteiro.
- Palavras vazias: `a o as os de da do das dos e em no na nos nas com para pra por`.
- Busca de candidatos: limite total 10; até 10 do mesmo dia com `similarity` ≥ 0,3 no título ou festival.
- Toda fusão é logada em WARNING; `agenda deduplicar` sem `--aplicar` não altera o banco.
- Comandos de teste rodam em `backend/`: `uv run pytest ...`.

## Review Focus

1. Dois festivais diferentes no mesmo dia e na mesma cidade com nomes que compartilham só tokens genéricos ("Festival MADA 2026" × "Festival DoSol 2026", razão 0,81 no texto inteiro): não podem ser fundidos — a razão compara só os tokens que diferem (teste na Task 3).
2. Título curto contido num longo no mesmo dia ("Jazz" × "Jazz no Bar de Nazaré") é fundido por decisão do usuário; título só de palavras vazias não funde nada (teste na Task 3).
3. Post de festival em que só um item tem `festival` e os outros não: só esse é agrupado; os outros seguem intactos (teste na Task 2).
4. Fusão em que os dois eventos já têm fonte do mesmo post: a fonte duplicada é descartada sem violar `uq_evento_fontes_evento_post` (teste na Task 5).
5. Reconciliação com par forte em que o modelo insiste em NOVO: após as tentativas, aplica DUPLICADO no par (teste na Task 4).

---

### Task 1: Campo `festival` (schema, prompt, coluna, mapeamento)

**Files:**
- Modify: `backend/src/agenda/extracao/schema.py` (campo), `backend/src/agenda/extracao/extrator.py` (regra no prompt)
- Modify: `backend/src/agenda/models.py` (`Evento.festival`, índice trgm `ix_eventos_festival_trgm`)
- Create: `backend/migrations/versions/0002_evento_festival.py`
- Modify: `backend/src/agenda/reconciliacao/decisao.py` (`Campo` e `_candidato_json` incluem `festival`), `backend/src/agenda/reconciliacao/aplicar.py` (`campos_do_evento` e `_ORDEM` incluem `festival`)
- Modify (construtores de `EventoExtraido`, `festival=None`): `tests/reconciliacao/fabricas.py`, `tests/extracao/test_regras.py`, `tests/avaliacao/test_golden.py`, `tests/fixtures/openai/extracao_varios_eventos.json`, `src/agenda/avaliacao/golden.py::_evento_extraido`
- Test: `tests/reconciliacao/test_aplicar.py`

**Interfaces:** Produces: `EventoExtraido.festival: str | None`; `Evento.festival: Mapped[str | None]`; `campos_do_evento(e)["festival"]`.

- [ ] **Step 1:** Teste `test_campos_do_evento_mapeia_festival`: `campos_do_evento(extraido(titulo="X", data_inicio=..., festival="Festival MADA 2026"))["festival"] == "Festival MADA 2026"`; e `test_duplicado_preenche_festival_vazio`: DUPLICADO sobre evento sem festival grava `ev.festival`.
- [ ] **Step 2:** Rodar `uv run pytest tests/reconciliacao/test_aplicar.py -k festival` → FAIL.
- [ ] **Step 3:** Implementar: campo no schema (depois de `artistas`); prompt com o texto da spec §3.1; coluna + migração `0002` (`add_column` + índice gin trgm; `downgrade` remove os dois); `festival` em `Campo`, `_ORDEM` (depois de `artistas`), `campos_do_evento`, `_candidato_json`; `festival=None`/`"festival": null` nos construtores listados.
- [ ] **Step 4:** `uv run pytest -q` → todos passam.
- [ ] **Step 5:** Commit `feat: campo festival na extração e em eventos`.

### Task 2: `agrupar_festivais`

**Files:**
- Modify: `backend/src/agenda/extracao/regras.py`; `backend/src/agenda/pipeline.py` (`tratar_reconciliar_post`: `agrupar_festivais(filtrar_validos(...))`); `backend/src/agenda/avaliacao/golden.py` (`avaliar_extracao` pontua `agrupar_festivais(res.extracao.eventos)`)
- Test: `tests/extracao/test_regras.py`

**Interfaces:** Consumes `EventoExtraido.festival`. Produces `agrupar_festivais(eventos: list[EventoExtraido]) -> list[EventoExtraido]` (ordem: grupos na posição do primeiro membro; sem festival intactos).

- [ ] **Step 1:** Testes (com `ev()` de `test_regras.py`):
  - `test_agrupa_atracoes_do_festival_por_dia`: 3 eventos `festival="Festival MADA 2026"` (2 em 16/10, 1 em 17/10) → 2 eventos; títulos `"Festival MADA 2026"`; `categoria == "festival"`; artistas do 16/10 = união na ordem.
  - `test_agrupa_local_divergente_vira_null_e_igual_mantem`: locais "Arena das Dunas"/"Arena das Dunas" → mantém; "Palco A"/"Palco B" → `None`; cidade idem.
  - `test_agrupa_hora_mais_cedo_e_descricao_por_atracao`: 21:00 e 16:00 → `hora_inicio == time(16,0)`; `descricao` contém os dois títulos originais.
  - `test_agrupa_status_esgotado_se_algum_e_cancelado_so_se_todos`.
  - `test_evento_sem_festival_passa_intacto` (inclui post com um item com festival e outro sem: só o primeiro muda).
  - `test_nome_do_festival_normalizado_agrupa` ("Festival MADA 2026" e "festival mada 2026" no mesmo dia → 1 evento).
- [ ] **Step 2:** `uv run pytest tests/extracao/test_regras.py -k agrup` → FAIL.
- [ ] **Step 3:** Implementar conforme spec §3.2 (chave `(normalizar(festival), data_inicio)`; `normalizar` vem da Task 3 — se a Task 3 ainda não existir, criar `identidade.normalizar` aqui e a Task 3 a reutiliza). `confianca`: mínimo por campo. `data_fim=None`.
- [ ] **Step 4:** `uv run pytest -q` → passa.
- [ ] **Step 5:** Commit `feat: agrupa atrações de festival em um evento por dia`.

### Task 3: Identidade determinística

**Files:**
- Create: `backend/src/agenda/reconciliacao/identidade.py`
- Test: `tests/reconciliacao/test_identidade.py`

**Interfaces:** Produces `normalizar(t: str | None) -> str`, `tokens(t: str | None) -> set[str]`, `cidade_norm(c: str | None) -> str`, `nomes_parecidos(a: str | None, b: str | None) -> bool`, `mesmo_evento(a: Evento, b: Evento) -> bool` (aceita `Evento` transiente, não persistido).

- [ ] **Step 1:** Testes com `Evento(...)` transientes:
  - `nomes_parecidos`: "Festival Dosol 2026" × "Festival Dosol 2026 na Sede Cultural Dosol" → True; "Jazz" × "Jazz no Bar de Nazaré" → True; "Festival MADA 2026" × "Festival DoSol 2026" → False; "Festival X 2026" × "Festival Y 2026" → False; "Baile da Amada com Belisa" × "Baile da Amada com Jader" → False; "Zeca Pagodino" × "Zeca Pagodinho" → True; "de da do" × "Show" → False; None → False.
  - `cidade_norm("ARACAJU/SE") == "aracaju"`, `cidade_norm("Natal/RN") == "natal"`.
  - `mesmo_evento`: mesmo dia + título parecido → True; outro dia → False; cidades "Aracaju" × "Salvador" → False; cidade só de um lado → True; ambos `hora_definida` 16h × 21h sem festival → False; mesma situação com `festival` nos dois → True; títulos diferentes mas `festival` parecido nos dois → True.
- [ ] **Step 2:** `uv run pytest tests/reconciliacao/test_identidade.py` → FAIL (módulo inexistente).
- [ ] **Step 3:** Implementar conforme spec §4.
- [ ] **Step 4:** Passa.
- [ ] **Step 5:** Commit `feat: identidade determinística de eventos`.

### Task 4: Candidatos do mesmo dia e reconciliação com par forte

**Files:**
- Modify: `backend/src/agenda/reconciliacao/candidatos.py` (`buscar_candidatos(..., limite: int = 10)`, critério do mesmo dia)
- Modify: `backend/src/agenda/reconciliacao/decisao.py` (`Reconciliador.decidir(e, candidatos, post, *, exigir_candidato: bool = False)`; idem em `OpenAIReconciliador` e `FakeReconciliador`; frase extra no texto do usuário quando `exigir_candidato`; `validar` rejeita NOVO; após `RespostaInvalida`, devolve `Decisao("DUPLICADO", par.id, [], "par forte; modelo não decidiu")` com o uso da exceção)
- Modify: `backend/src/agenda/pipeline.py` (`par_forte`), `backend/src/agenda/reconciliacao/aplicar.py` (remove `_casamento_forte`, `_parecidos`, `_norm` e seus imports)
- Test: `tests/reconciliacao/test_candidatos.py`, `tests/reconciliacao/test_decisao.py`, `tests/test_pipeline.py`, `tests/reconciliacao/test_aplicar.py` (remove os 6 testes de casamento forte; a cobertura passa para `test_identidade.py` e `test_pipeline.py`)

**Interfaces:** Consumes `mesmo_evento`, `campos_do_evento`, `eventos_do_post`. Produces `par_forte(s: Session, e: EventoExtraido, candidatos: list[Evento], post: Post) -> Evento | None` em `pipeline.py` (candidatos de outro post com `mesmo_evento(Evento(**campos_do_evento(e)), c)`; mais fontes, depois menor id).

- [ ] **Step 1:** Testes:
  - candidatos: 12 eventos "Festival Dosol 2026" em datas anteriores + 1 em 05/12 → o de 05/12 está no resultado para extraído de 05/12.
  - decisão (cliente falso de `test_decisao.py`): com `exigir_candidato=True` e o modelo respondendo NOVO em todas as tentativas → `DUPLICADO` com `evento_id` do candidato.
  - pipeline: evento existente de outro post "Festival Dosol 2026 na Sede Cultural Dosol" em 05/12; post novo com "Festival Dosol 2026" em 05/12; reconciliador falso registra os candidatos recebidos e `exigir_candidato` → recebeu só o par e `True`; nenhum evento novo criado.
  - Ajustar a classe reconciliadora local de `test_pipeline.py` para aceitar `**kw`.
- [ ] **Step 2:** Rodar → FAIL.
- [ ] **Step 3:** Implementar. Em `tratar_reconciliar_post`: `par = par_forte(...)`; `decidir(e, [par] if par else candidatos, post, exigir_candidato=par is not None)`; `aplicar(s, e, decisao, [par] if par else candidatos, post)`.
- [ ] **Step 4:** `uv run pytest -q` → passa.
- [ ] **Step 5:** Commit `feat: reconciliação com par forte determinístico`.

### Task 5: Fusão, varredura, CLI e worker

**Files:**
- Create: `backend/src/agenda/reconciliacao/fusao.py`
- Modify: `backend/src/agenda/pipeline.py` (fim de `tratar_reconciliar_post`: `deduplicar(s, eventos_tocados)`), `backend/src/agenda/cli.py` (comando `deduplicar`), `backend/README.md` (uma linha na seção "Consultar e corrigir")
- Test: `tests/reconciliacao/test_fusao.py`, `tests/test_cli.py`, `tests/test_pipeline.py`

**Interfaces:** Consumes `mesmo_evento`, `_duplicado`-like preenchimento (reusar `_falta`/`_alterar` de `aplicar.py`). Produces `fundir(s: Session, manter: Evento, remover: Evento, motivo: str) -> None`, `deduplicar(s: Session, *, agora: datetime, eventos: list[Evento] | None = None) -> list[tuple[int, int]]` (pares `(manter_id, removido_id)`).

- [ ] **Step 1:** Testes:
  - `fundir`: fontes de `remover` passam a `manter`; fonte do mesmo post nos dois → uma só; revisões movidas; campo vazio de `manter` preenchido com revisão (`motivo`); hora acrescentada no mesmo dia; artistas unidos; `status` ativo × esgotado → esgotado; `remover` apagado.
  - `deduplicar`: 3 eventos parecidos no mesmo dia → 1 resta (o de mais fontes) e 2 pares devolvidos; par em dias diferentes intacto; evento passado há mais de 7 dias ignorado; com `eventos=[x]` só varre o dia de `x`.
  - CLI: `deduplicar` sem `--aplicar` lista e não apaga; com `--aplicar` apaga.
  - pipeline: duas duplicatas pré-existentes no dia de um evento que o post toca → fundidas ao fim do job.
- [ ] **Step 2:** Rodar → FAIL.
- [ ] **Step 3:** Implementar conforme spec §8 (`manter` = mais fontes, empate menor id; WARNING por fusão; CLI imprime `manter_id <- removido_id  titulo (dia)` por fusão e o total).
- [ ] **Step 4:** `uv run pytest -q` → passa.
- [ ] **Step 5:** Commit `feat: fusão de eventos duplicados (worker e agenda deduplicar)`.

### Task 6: Golden set e aceite nos dados reais

**Files:**
- Modify: `backend/golden/casos/mada_lineup/esperado.json` (2 eventos, 16 e 17/10, título "Festival MADA 2026", `festival` igual, categoria festival)
- Create: `backend/golden/casos/dosol_siba_festival/` e `backend/golden/casos/mada_baile_amada/` (post real exportado + `esperado.json`: evento do festival no dia, artista da atração em `artistas`; reconciliação: candidato do festival no mesmo dia com título variante → DUPLICADO)

- [ ] **Step 1:** Exportar os posts reais (Siba no DoSol 28/11; um "Baile da Amada" do MADA) com o script de exportação já usado e anotar.
- [ ] **Step 2:** `uv run agenda avaliar --etapa extracao --golden golden/casos` e `--etapa reconciliacao` → registrar números.
- [ ] **Step 3:** Reprocessar os 134 posts (backup das tabelas de eventos antes; reenfileirar extração do mais antigo ao mais novo), rodar `worker --uma-vez` e `worker-reconciliacao --uma-vez`.
- [ ] **Step 4:** Aceite: `uv run agenda deduplicar` (simulação) não lista nada; `uv run agenda eventos` mostra MADA em 16/10 e 17/10 (um cada), DoSol um por dia, Jambu um por cidade, Jáder/Giovanna/Black Pantera próprios.
- [ ] **Step 5:** Commit `test: golden de festivais e aceite da deduplicação`.
