# Fatia 1 — Núcleo de Dados Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Coletar posts de perfis do Instagram, extrair eventos com a OpenAI, reconciliá-los com o banco (novo / duplicado / atualização) e operar tudo por uma CLI de admin.

**Architecture:** Pacote Python `agenda` em `backend/`. Postgres é a fonte da verdade e também a fila de jobs (`FOR UPDATE SKIP LOCKED`). O pipeline é uma cadeia de jobs (`coletar_perfil` → `extrair_post` → `reconciliar_post`); coleta, extração e reconciliação ficam atrás de interfaces (`Coletor`, `Extrator`, `Reconciliador`) para que os testes usem falsos e gravações. A reconciliação roda em série.

**Tech Stack:** Python 3.12, SQLAlchemy 2 + Alembic, psycopg 3, Postgres 16 (`pg_trgm`), pydantic v2 / pydantic-settings, openai SDK, instaloader, boto3 (MinIO), Pillow, Typer, pytest + testcontainers, Docker Compose, uv.

**Spec:** `docs/superpowers/specs/2026-10-09-agenda-cultural-instagram-design.md` (seções 3, 4 e 7–10; sem usuários, grupos nem Telegram, que são das Fatias 2 e 3).

## Global Constraints

- Fuso horário `America/Sao_Paulo`; datas guardadas como `timestamptz`.
- `categoria` ∈ `show, festa, exposicao, teatro, cinema, oficina, festival, outro`.
- Só vira evento o que tem `titulo` e `data_inicio`; eventos com data passada são descartados.
- Imagens redimensionadas para lado máximo de 1024px antes da visão; originais salvos no storage S3-compatível.
- Modelos por variável de ambiente: `OPENAI_MODELO_EXTRACAO`, `OPENAI_MODELO_RECONCILIACAO`.
- Busca de candidatos: no máximo 5; inclui eventos até 7 dias no passado; não exige a mesma data.
- Reconciliação em série (um único consumidor do tipo `reconciliar_post`); `evento_id` fora dos candidatos é resposta inválida.
- Retry com backoff exponencial até `max_tentativas`; depois `status = erro`.
- Cada post registra `tokens_entrada`, `tokens_saida`, `custo_estimado`, `modelo_extracao`.
- Scraper usa contas dedicadas (nunca a pessoal), sessão criptografada, limite por conta/hora, backoff em bloqueio.
- `username` de perfil é minúsculo, sem `@`.

## Review Focus

1. Flyer de "agenda do mês" com várias datas: um post gera N eventos, não um só (Task 7, Task 10).
2. Post de dezembro que cita "10/01" ou "sexta que vem": o ano e a data relativa são resolvidos a partir da data do post (Task 7).
3. Mesmo título em locais diferentes, ou dois shows no mesmo local e dia com artistas diferentes: não são duplicados (Task 9, Task 10).
4. Post só com vídeo, sem imagem, ou com carrossel de 10 imagens: não quebra a coleta nem a extração (Task 6, Task 8).
5. Dois jobs inserindo o mesmo `shortcode` ao mesmo tempo, e reprocessar um post já reconciliado: sem post duplicado e sem evento duplicado (Task 3, Task 6, Task 11).

---

## Estrutura de arquivos

```
docker-compose.yml                      # postgres, minio
backend/pyproject.toml
backend/alembic.ini, backend/migrations/
backend/src/agenda/
  config.py        # Settings
  db.py            # engine, SessionLocal, session_scope
  models.py        # tabelas
  jobs.py          # fila no Postgres
  imagens.py       # redimensionar
  storage.py       # Storage, S3Storage
  coleta/base.py            # Coletor, PostColetado, exceções
  coleta/instaloader_coletor.py
  coleta/pool.py            # contas, rate limit, bloqueio
  coleta/servico.py         # coletar_perfil, agendador
  extracao/schema.py        # EventoExtraido
  extracao/regras.py        # filtros e normalização
  extracao/extrator.py      # Extrator, OpenAIExtrator
  reconciliacao/candidatos.py
  reconciliacao/decisao.py  # Decisao, Reconciliador, OpenAIReconciliador
  reconciliacao/aplicar.py  # efeitos transacionais
  pipeline.py      # handlers dos jobs
  worker.py        # loop
  cli.py           # Typer
  avaliacao/       # golden set + script
backend/tests/...  # espelha src/
```

---

### Task 1: Esqueleto, Docker Compose e configuração

**Files:**
- Create: `docker-compose.yml`, `backend/pyproject.toml`, `backend/.env.example`, `backend/src/agenda/__init__.py`, `config.py`, `db.py`, `backend/tests/conftest.py`
- Test: `backend/tests/test_config.py`, `backend/tests/test_db.py`

**Interfaces:**
- Produces: `Settings` (pydantic-settings) com `database_url`, `openai_api_key`, `openai_modelo_extracao`, `openai_modelo_reconciliacao`, `s3_endpoint`, `s3_bucket`, `s3_access_key`, `s3_secret_key`, `chave_sessao` (Fernet); `get_settings() -> Settings` (cacheado). `db.session_scope() -> ContextManager[Session]` (commit/rollback). Fixture `session` em `conftest.py`: Postgres real via testcontainers, esquema criado por Alembic (a fixture passa a funcionar de verdade na Task 2), cada teste em transação revertida.

- [ ] **Step 1:** Escrever `test_config.py::test_settings_le_variaveis_de_ambiente` (monkeypatch `OPENAI_MODELO_EXTRACAO=x`, assert `get_settings().openai_modelo_extracao == "x"`) e `test_db.py::test_session_scope_faz_rollback_em_erro` (usa SQLite em memória só para esse teste de contrato do context manager).
- [ ] **Step 2:** Rodar `cd backend && uv run pytest tests/test_config.py tests/test_db.py -v`. Esperado: FAIL (módulos inexistentes).
- [ ] **Step 3:** Criar `pyproject.toml` (pacote `agenda` em `src/`, dependências da stack, script `agenda = "agenda.cli:app"`), `docker-compose.yml` (postgres:16 com `pg_trgm` habilitável, minio com bucket `flyers` criado por `mc`), `config.py`, `db.py`.
- [ ] **Step 4:** Rodar os mesmos testes. Esperado: PASS.
- [ ] **Step 5:** `git add -A && git commit -m "feat: scaffold backend, compose e settings"`.

### Task 2: Esquema do banco e migrações

**Files:**
- Create: `backend/src/agenda/models.py`, `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/versions/0001_inicial.py`
- Modify: `backend/tests/conftest.py` (fixture `session` passa a aplicar `alembic upgrade head`)
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Produces: modelos SQLAlchemy `Perfil`, `ContaColeta`, `Post`, `Evento`, `EventoFonte`, `RevisaoEvento`, `Job` com os campos da spec seção 4 (tabelas de usuários/grupos ficam para a Fatia 2). Constraints: `perfis.username` único; `posts.shortcode` único; `evento_fontes (evento_id, post_id)` único. Índices GIN `gin_trgm_ops` em `eventos.titulo` e `eventos.local_nome`; índice em `eventos.inicio`. A migração executa `CREATE EXTENSION IF NOT EXISTS pg_trgm`. Enums como `String` com `CheckConstraint`. `jobs.chave` (texto, nulo) com índice único parcial sobre `(tipo, chave)` onde `status <> 'concluido'`.

- [ ] **Step 1:** Escrever testes: `test_shortcode_duplicado_levanta_integrity_error`, `test_username_unico`, `test_evento_fonte_duplicada_levanta_integrity_error`, `test_categoria_invalida_rejeitada` (CheckConstraint), `test_pg_trgm_disponivel` (`SELECT similarity('abc','abd')` > 0).
- [ ] **Step 2:** Rodar `uv run pytest tests/test_models.py -v`. Esperado: FAIL.
- [ ] **Step 3:** Implementar `models.py` e a migração `0001_inicial` (escrita à mão, não autogerada, para incluir a extensão e os índices).
- [ ] **Step 4:** Rodar os testes. Esperado: PASS.
- [ ] **Step 5:** Commit `feat: esquema do banco e migração inicial`.

### Task 3: Fila de jobs no Postgres

**Files:**
- Create: `backend/src/agenda/jobs.py`
- Test: `backend/tests/test_jobs.py`

**Interfaces:**
- Consumes: `Job`, `session_scope` (Tasks 1–2).
- Produces:
  - `enfileirar(s: Session, tipo: str, payload: dict, *, executar_em: datetime | None = None, max_tentativas: int = 5, chave: str | None = None) -> Job | None` — com `chave`, é idempotente (não enfileira se já existir job não concluído com o mesmo tipo e chave; retorna `None`). Requer coluna `chave` com índice único parcial em jobs não concluídos (incluir na migração da Task 2).
  - `reservar(s: Session, tipos: list[str]) -> Job | None` — `FOR UPDATE SKIP LOCKED`, só jobs `pendente` com `executar_em <= now()`, marca `executando`.
  - `concluir(s, job)`; `falhar(s, job, erro: str)` — incrementa `tentativas`, reagenda com backoff `2**tentativas * 30s`, ou `status = erro` ao atingir `max_tentativas`.

- [ ] **Step 1:** Testes: `test_reservar_respeita_executar_em`, `test_reservar_nao_entrega_o_mesmo_job_a_duas_sessoes` (duas sessões/threads), `test_falhar_aplica_backoff_exponencial`, `test_falhar_esgota_tentativas_vira_erro`, `test_enfileirar_com_chave_e_idempotente`.
- [ ] **Step 2:** Rodar `uv run pytest tests/test_jobs.py -v`. Esperado: FAIL.
- [ ] **Step 3:** Implementar `jobs.py`.
- [ ] **Step 4:** Rodar. Esperado: PASS.
- [ ] **Step 5:** Commit `feat: fila de jobs no postgres`.

### Task 4: Imagens e storage

**Files:**
- Create: `backend/src/agenda/imagens.py`, `backend/src/agenda/storage.py`
- Test: `backend/tests/test_imagens.py`, `backend/tests/test_storage.py`

**Interfaces:**
- Produces:
  - `redimensionar(dados: bytes, lado_max: int = 1024) -> bytes` — JPEG; mantém proporção; não amplia imagem menor.
  - `Storage` (Protocol): `salvar(chave: str, dados: bytes, content_type: str) -> None`; `ler(chave: str) -> bytes`.
  - `S3Storage(endpoint, bucket, access_key, secret_key)` (boto3) e `MemoriaStorage` (dict, para testes).

- [ ] **Step 1:** Testes: `test_redimensionar_limita_lado_maior_a_1024` (imagem 3000×1500 → 1024×512), `test_redimensionar_nao_amplia`, `test_redimensionar_aceita_png_com_alpha`, `test_memoria_storage_roundtrip`.
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar com Pillow e boto3. `S3Storage` fica sem teste automatizado (fina demais); verificação manual contra o MinIO na Task 12.
- [ ] **Step 4:** Rodar. Esperado: PASS.
- [ ] **Step 5:** Commit `feat: redimensionamento de imagens e storage`.

### Task 5: Interface `Coletor` e scraper próprio

**Files:**
- Create: `backend/src/agenda/coleta/base.py`, `coleta/instaloader_coletor.py`, `coleta/pool.py`
- Test: `backend/tests/coleta/test_instaloader_parser.py`, `test_pool.py`, `backend/tests/fixtures/ig/*.json`

**Interfaces:**
- Produces:
  - `PostColetado` (dataclass): `shortcode: str`, `legenda: str`, `publicado_em: datetime`, `urls_imagens: list[str]` (vazia para vídeo sem capa).
  - `Coletor` (Protocol): `posts_desde(username: str, desde: datetime | None) -> Iterable[PostColetado]`, mais novos primeiro.
  - Exceções: `PerfilPrivado`, `PerfilInexistente`, `ContaBloqueada`.
  - `FakeColetor(posts_por_perfil: dict[str, list[PostColetado]], erros: dict[str, Exception] | None = None)` em `coleta/base.py`.
  - `InstaloaderColetor(pool: PoolContas)`; função pura `parse_post(node: dict) -> PostColetado` (carrossel → todas as imagens; vídeo → capa).
  - `PoolContas(session_factory, limite_por_hora: int)`: `obter() -> ContaColeta` (escolhe conta ativa, não bloqueada e abaixo do limite horário; levanta `SemContasDisponiveis`), `marcar_bloqueada(conta, ate: datetime)`.

- [ ] **Step 1:** Testes com fixtures JSON gravadas: `test_parse_carrossel_retorna_todas_as_imagens`, `test_parse_video_usa_capa`, `test_parse_legenda_ausente_vira_string_vazia`, `test_pool_pula_conta_bloqueada`, `test_pool_respeita_limite_por_hora`, `test_pool_sem_contas_levanta`.
- [ ] **Step 2:** Rodar `uv run pytest tests/coleta -v`. Esperado: FAIL.
- [ ] **Step 3:** Implementar. A sessão da conta é descriptografada com Fernet (`chave_sessao`). Erros do instaloader são mapeados para as exceções acima.
- [ ] **Step 4:** Rodar. Esperado: PASS.
- [ ] **Step 5:** Commit `feat: interface Coletor, parser e pool de contas`.

### Task 6: Serviço de coleta e agendador

**Files:**
- Create: `backend/src/agenda/coleta/servico.py`
- Test: `backend/tests/coleta/test_servico.py`

**Interfaces:**
- Consumes: `Coletor`, `PoolContas`, `Storage`, `redimensionar`/original, `enfileirar`, modelos.
- Produces:
  - `coletar_perfil(s: Session, perfil_id: int, coletor: Coletor, storage: Storage, *, agora: datetime) -> int` — retorna a quantidade de posts novos. Coleta desde `ultima_coleta_em` (ou 30 dias na primeira vez). Para ao encontrar shortcode já salvo. Salva imagens em `posts/{shortcode}/{n}.jpg`, cria `Post(status="pendente")` e enfileira `extrair_post` (chave `extrair:{post_id}`). Trata `PerfilPrivado` e `PerfilInexistente` atualizando `perfis.status`; `ContaBloqueada` propaga (o job é reagendado).
  - `agendar_coletas(s: Session, agora: datetime) -> int` — enfileira `coletar_perfil` para perfis `ativo` com `proxima_coleta_em <= agora`, com `chave = f"coletar:{perfil_id}"` e `executar_em` com jitter aleatório de 0–30 min. Na Fatia 1, todo perfil `ativo` conta (grupos só existem na Fatia 2).

- [ ] **Step 1:** Testes com `FakeColetor` e `MemoriaStorage`: `test_primeira_coleta_busca_30_dias`, `test_coleta_incremental_para_no_shortcode_conhecido`, `test_post_so_com_video_sem_imagem_vira_post_sem_imagens`, `test_carrossel_de_10_imagens_salva_as_10`, `test_perfil_privado_atualiza_status_e_nao_levanta`, `test_shortcode_ja_existente_nao_duplica` (insere o mesmo shortcode já salvo por outro job), `test_agendar_nao_duplica_job_pendente`.
- [ ] **Step 2:** Rodar `uv run pytest tests/coleta/test_servico.py -v`. Esperado: FAIL.
- [ ] **Step 3:** Implementar. Inserção de post com `ON CONFLICT (shortcode) DO NOTHING` para a corrida entre jobs.
- [ ] **Step 4:** Rodar. Esperado: PASS.
- [ ] **Step 5:** Commit `feat: serviço de coleta incremental e agendador`.

### Task 7: Schema de extração e regras pós-extração

**Files:**
- Create: `backend/src/agenda/extracao/schema.py`, `extracao/regras.py`
- Test: `backend/tests/extracao/test_regras.py`

**Interfaces:**
- Produces:
  - `EventoExtraido` (pydantic) com os campos da spec 3.4 (inclui `status_indicado`, `confianca`) e `ExtracaoPost(eventos: list[EventoExtraido])`; `model_json_schema()` é o JSON Schema enviado à OpenAI.
  - `filtrar_validos(eventos: list[EventoExtraido], agora: datetime) -> list[EventoExtraido]` — descarta sem `titulo`/`data_inicio` e com data passada (comparando em `America/Sao_Paulo`; um evento de hoje é mantido).
  - `para_inicio(e: EventoExtraido) -> tuple[datetime, bool]` — `(timestamptz em America/Sao_Paulo, hora_definida)`; sem hora → 00:00 e `False`.
  - `normalizar_preco(e) -> EventoExtraido` — `gratuito=True` zera `preco_min/max`; `min > max` troca os valores.
  - `instrucoes_datas(publicado_em: datetime) -> str` — trecho de prompt com a data do post, o dia da semana e a regra do ano ("se o dia/mês já passou em relação à data do post, assuma o ano seguinte").

- [ ] **Step 1:** Testes: `test_filtra_sem_titulo`, `test_filtra_sem_data`, `test_filtra_data_passada_e_mantem_hoje`, `test_post_com_varios_eventos_mantem_todos` (10 eventos → 10), `test_sem_hora_marca_hora_definida_false`, `test_hora_apos_meia_noite_mantem_o_dia_do_evento` ("sábado 01h" fica no dia informado, sem somar um dia), `test_gratuito_zera_precos`, `test_preco_min_maior_que_max_e_trocado`, `test_instrucoes_datas_contem_ano_seguinte_para_dezembro` (post de 2026-12-20; a instrução cita 2026-12-20 e a regra do ano).
- [ ] **Step 2:** Rodar `uv run pytest tests/extracao/test_regras.py -v`. Esperado: FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar. Esperado: PASS.
- [ ] **Step 5:** Commit `feat: schema de extração e regras pós-extração`.

### Task 8: Extrator OpenAI (Etapa A)

**Files:**
- Create: `backend/src/agenda/extracao/extrator.py`
- Test: `backend/tests/extracao/test_extrator.py`, `backend/tests/fixtures/openai/extracao_*.json`

**Interfaces:**
- Consumes: `ExtracaoPost`, `instrucoes_datas`, `Storage`, `redimensionar`.
- Produces:
  - `Resultado(extracao: ExtracaoPost, tokens_entrada: int, tokens_saida: int, custo: Decimal, modelo: str)`.
  - `Extrator` (Protocol): `extrair(legenda: str, imagens: list[bytes], username: str, publicado_em: datetime) -> Resultado`.
  - `OpenAIExtrator(client, modelo: str)`: chamada com imagens em base64 (já redimensionadas) e saída estruturada pelo JSON Schema; uma nova tentativa quando a resposta não valida; levanta `RespostaInvalida` depois. `FakeExtrator(respostas: dict[str, ExtracaoPost])` por `username` para testes.
  - `custo` calculado a partir de uma tabela de preços por modelo em `config.py` (`PRECOS_POR_MILHAO: dict[str, tuple[Decimal, Decimal]]`).

- [ ] **Step 1:** Testes com um cliente falso gravado: `test_extrai_varios_eventos_de_um_flyer`, `test_post_sem_evento_retorna_lista_vazia`, `test_resposta_invalida_tenta_de_novo_e_depois_levanta`, `test_envia_imagens_redimensionadas` (inspeciona o payload), `test_post_sem_imagens_envia_so_legenda`, `test_calcula_custo_pelos_tokens`.
- [ ] **Step 2:** Rodar `uv run pytest tests/extracao/test_extrator.py -v`. Esperado: FAIL.
- [ ] **Step 3:** Implementar `OpenAIExtrator` com o prompt do sistema em constante no módulo (instruções: lista fixa de categorias, cidade obrigatória quando inferível, `confianca` por campo crítico, não inventar o que não está no post).
- [ ] **Step 4:** Rodar. Esperado: PASS.
- [ ] **Step 5:** Commit `feat: extrator OpenAI com visão`.

### Task 9: Busca de candidatos (Etapa B)

**Files:**
- Create: `backend/src/agenda/reconciliacao/candidatos.py`
- Test: `backend/tests/reconciliacao/test_candidatos.py`

**Interfaces:**
- Consumes: `EventoExtraido`, `Evento`, `para_inicio`.
- Produces: `buscar_candidatos(s: Session, e: EventoExtraido, *, limite: int = 5, limiar_titulo: float = 0.4) -> list[Evento]`. Critérios (qualquer um): similaridade de título ≥ limiar; interseção de `artistas` (comparação sem acento e minúscula); mesmo `local_nome` (similaridade ≥ 0,5) no mesmo dia. Apenas eventos com `inicio >= agora - 7 dias`. Ordenados por escore combinado decrescente.

- [ ] **Step 1:** Testes: `test_encontra_por_titulo_similar_com_data_diferente` (adiamento), `test_encontra_por_artista_em_comum`, `test_encontra_por_local_e_dia`, `test_ignora_evento_com_mais_de_7_dias_no_passado`, `test_respeita_limite_de_5`, `test_mesmo_titulo_em_outro_local_ainda_e_candidato_mas_nao_o_unico` (retorna os candidatos; a decisão cabe à IA), `test_sem_candidatos_retorna_lista_vazia`.
- [ ] **Step 2:** Rodar `uv run pytest tests/reconciliacao/test_candidatos.py -v`. Esperado: FAIL.
- [ ] **Step 3:** Implementar com SQL (`similarity()`, `&&` em arrays após normalização) via SQLAlchemy.
- [ ] **Step 4:** Rodar. Esperado: PASS.
- [ ] **Step 5:** Commit `feat: busca de candidatos com pg_trgm`.

### Task 10: Reconciliação (Etapa C)

**Files:**
- Create: `backend/src/agenda/reconciliacao/decisao.py`, `reconciliacao/aplicar.py`
- Test: `backend/tests/reconciliacao/test_decisao.py`, `test_aplicar.py`

**Interfaces:**
- Consumes: `buscar_candidatos`, `EventoExtraido`, `Post`, `Evento`, `EventoFonte`, `RevisaoEvento`.
- Produces:
  - `Decisao` (pydantic): `decisao: Literal["NOVO","DUPLICADO","ATUALIZACAO"]`, `evento_id: int | None`, `mudancas: list[Mudanca]` (`campo: str`, `valor_novo: Any`), `motivo: str`.
  - `Reconciliador` (Protocol): `decidir(e: EventoExtraido, candidatos: list[Evento], post: Post) -> tuple[Decisao, Resultado]`; `OpenAIReconciliador(client, modelo)` (só texto, saída estruturada, uma nova tentativa quando inválida); `FakeReconciliador(decisoes)` para testes. Sem candidatos, `OpenAIReconciliador` não chama a API: retorna `NOVO`.
  - `aplicar(s: Session, e: EventoExtraido, d: Decisao, candidatos: list[Evento], post: Post) -> Evento` — numa transação: `NOVO` cria o evento + fonte; `DUPLICADO` cria a fonte e preenche só campos nulos do evento (uma revisão por campo); `ATUALIZACAO` aplica `mudancas` (campos permitidos: `titulo, descricao, inicio, fim, local_nome, endereco, cidade, categoria, preco_*, gratuito, link_ingresso, artistas, status`), uma `RevisaoEvento` por campo. Levanta `DecisaoInvalida` quando `evento_id` não está em `candidatos` ou `campo` não é permitido. `status_indicado` do evento extraído vira `mudanca` de `status` quando a decisão é `ATUALIZACAO`.

- [ ] **Step 1:** Testes de `aplicar`: `test_novo_cria_evento_e_fonte`, `test_duplicado_so_vincula_fonte`, `test_duplicado_preenche_link_ingresso_nulo_e_registra_revisao`, `test_atualizacao_registra_revisao_por_campo_com_antes_e_depois`, `test_adiado_muda_status_e_data`, `test_evento_id_fora_dos_candidatos_levanta`, `test_campo_nao_permitido_levanta`, `test_falha_no_meio_nao_deixa_efeito_parcial` (rollback), `test_reprocessar_mesmo_post_nao_duplica_fonte`. Testes de `OpenAIReconciliador` com cliente falso: `test_sem_candidatos_nao_chama_api`, `test_resposta_invalida_tenta_de_novo`.
- [ ] **Step 2:** Rodar `uv run pytest tests/reconciliacao -v`. Esperado: FAIL.
- [ ] **Step 3:** Implementar. O prompt do reconciliador (constante no módulo) diz explicitamente: mesmo título com local ou data-base diferentes e sem pista de remarcação **não** é duplicado; dois shows com artistas diferentes no mesmo local e dia são eventos distintos.
- [ ] **Step 4:** Rodar. Esperado: PASS.
- [ ] **Step 5:** Commit `feat: reconciliação de eventos com IA`.

### Task 11: Handlers do pipeline e worker

**Files:**
- Create: `backend/src/agenda/pipeline.py`, `backend/src/agenda/worker.py`
- Test: `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: tudo acima.
- Produces:
  - `Dependencias` (dataclass): `coletor`, `storage`, `extrator`, `reconciliador`.
  - `tratar_coletar_perfil(s, job, deps)`; `tratar_extrair_post(s, job, deps)` (lê imagens do storage, grava `posts.extracao`, tokens e custo, status `extraido`, enfileira `reconciliar_post` com chave `reconciliar:{post_id}`); `tratar_reconciliar_post(s, job, deps)` (para cada evento válido: `buscar_candidatos` → `decidir` → `aplicar`; status `reconciliado`; idempotente para um post já `reconciliado`).
  - `rodar_worker(deps, tipos: list[str], *, uma_vez: bool = False, sleep=time.sleep) -> int` — reserva e executa jobs; em exceção chama `falhar`; se o job esgotar as tentativas, marca o post (quando houver) com `status = erro` e `erro_msg`, e registra um log `ERROR`. O worker de reconciliação é iniciado separadamente, com `tipos=["reconciliar_post"]`, e é um único processo.

- [ ] **Step 1:** Testes de ponta a ponta com os falsos e `MemoriaStorage`: `test_fluxo_completo_do_perfil_ao_evento`, `test_dois_posts_do_mesmo_show_geram_um_evento_com_duas_fontes`, `test_post_de_flyer_com_varios_eventos_cria_varios_eventos`, `test_post_sem_evento_vira_reconciliado_sem_eventos`, `test_erro_da_openai_reagenda_e_depois_marca_post_como_erro`, `test_reprocessar_post_reconciliado_nao_duplica`, `test_custo_e_tokens_gravados_no_post`.
- [ ] **Step 2:** Rodar `uv run pytest tests/test_pipeline.py -v`. Esperado: FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar a suíte inteira `uv run pytest -v`. Esperado: PASS.
- [ ] **Step 5:** Commit `feat: handlers do pipeline e worker`.

### Task 12: CLI de admin

**Files:**
- Create: `backend/src/agenda/cli.py`
- Test: `backend/tests/test_cli.py`

**Interfaces:**
- Produces (Typer, comando raiz `agenda`):
  - `agenda perfil-adicionar <username>` (normaliza para minúsculo sem `@`; idempotente) e `agenda perfil-listar`.
  - `agenda conta-adicionar <usuario_ig> --sessao-arquivo <path>` (criptografa e grava em `contas_coleta`).
  - `agenda coletar [--perfil <username>]` (enfileira a coleta imediatamente, prioridade).
  - `agenda worker [--tipos coletar_perfil,extrair_post] [--uma-vez]` e `agenda worker-reconciliacao [--uma-vez]`.
  - `agenda post-reprocessar <shortcode> [--etapa extracao|reconciliacao]` (zera o estado e reenfileira só a etapa pedida; reconciliação reaproveita `posts.extracao`).
  - `agenda eventos [--cidade X] [--de YYYY-MM-DD] [--ate YYYY-MM-DD]` (tabela com título, início, local, cidade, status, nº de fontes).

- [ ] **Step 1:** Testes com `typer.testing.CliRunner`: `test_perfil_adicionar_normaliza_username`, `test_perfil_adicionar_e_idempotente`, `test_post_reprocessar_reconciliacao_nao_apaga_extracao`, `test_eventos_filtra_por_cidade_e_periodo`.
- [ ] **Step 2:** Rodar `uv run pytest tests/test_cli.py -v`. Esperado: FAIL.
- [ ] **Step 3:** Implementar. Um `build_deps()` monta as dependências reais a partir de `Settings`.
- [ ] **Step 4:** Rodar a suíte. Esperado: PASS. Verificação manual: `docker compose up -d`, `uv run alembic upgrade head`, `uv run agenda perfil-adicionar <um perfil público de teste>`, `uv run agenda coletar`, `uv run agenda worker --uma-vez` (precisa de uma conta de coleta e de `OPENAI_API_KEY`), `uv run agenda eventos`. Esperado: eventos listados e imagens visíveis no MinIO.
- [ ] **Step 5:** Commit `feat: CLI de admin`.

### Task 13: Golden set e script de avaliação

**Files:**
- Create: `backend/src/agenda/avaliacao/golden.py`, `backend/src/agenda/avaliacao/cli.py` (registrado como `agenda avaliar`), `backend/golden/README.md`, `backend/golden/casos/` (diretórios por caso: `imagem*.jpg`, `legenda.txt`, `esperado.json`)
- Test: `backend/tests/avaliacao/test_golden.py`

**Interfaces:**
- Consumes: `Extrator`, `Reconciliador`.
- Produces: `carregar_casos(dir: Path) -> list[CasoGolden]`; `avaliar_extracao(casos, extrator) -> RelatorioExtracao` (acurácia por campo: `titulo` por similaridade ≥ 0,8, `data_inicio`/`hora_inicio`/`cidade`/`categoria` exatos, `artistas` por F1, `preco_*` com tolerância zero); `avaliar_reconciliacao(casos, reconciliador) -> RelatorioDecisao` (acerto da decisão e do `evento_id`). `agenda avaliar --etapa extracao|reconciliacao --golden backend/golden/casos` imprime o relatório. Formato de `esperado.json` documentado em `golden/README.md`, incluindo os casos de reconciliação (`candidatos` pré-definidos + `decisao_esperada`).

- [ ] **Step 1:** Testes com um `FakeExtrator` e 3 casos mínimos em `tests/fixtures/golden/`: `test_carregar_casos_le_esperado_json`, `test_relatorio_extracao_calcula_acuracia_por_campo` (um campo certo, um errado → 0,5), `test_relatorio_reconciliacao_conta_acertos_de_decisao`.
- [ ] **Step 2:** Rodar `uv run pytest tests/avaliacao -v`. Esperado: FAIL.
- [ ] **Step 3:** Implementar o carregador, as métricas e o comando. O comando **não** roda no CI e não faz parte de `pytest`.
- [ ] **Step 4:** Rodar a suíte inteira. Esperado: PASS. O usuário anota os ~50 casos reais em `backend/golden/casos/` (fora do escopo de código; o README descreve como). Incluir pelo menos: flyer com várias datas, adiamento, cancelamento, mesmo show divulgado por casa e artista, mesmo título em locais diferentes, post de dezembro com data de janeiro, post só com legenda.
- [ ] **Step 5:** Commit `feat: golden set e avaliação de extração e reconciliação`.

---

## Self-review

- **Cobertura da spec (Fatia 1, seção 10):** esqueleto + Compose (T1), esquema (T2), fila (T3), storage/imagens (T4), `Coletor` + scraper + pool (T5–T6), Etapas A/B/C (T8/T9/T10, regras em T7), pipeline (T11), CLI de admin (T12), golden set e avaliação (T13). Seção 7 (erros): retry/backoff e esgotamento em T3/T11, bloqueio de conta em T5, perfil privado em T6, resposta inválida em T8/T10. Seção 8 (custos): T8/T11. Os alertas de admin por Telegram são da Fatia 3; a Fatia 1 registra log `ERROR`.
- **Consistência de tipos:** `Resultado` é definido em T8 e reutilizado em T10; `Dependencias` agrega as interfaces de T5/T8/T10; `enfileirar(..., chave=)` de T3 é usado em T6 e T11, e a coluna `chave` é incluída na migração de T2.
- **Proporção:** plano com ~13 tarefas, assinaturas e nomes de teste sem corpos de função.
