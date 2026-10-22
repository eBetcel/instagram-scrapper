# Fonte Apify Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trocar a coleta do Instagram (instaloader + contas) pela API da Apify, em lotes agendados duas vezes por dia, e remover todo o scraper antigo.

**Architecture:** Um cliente REST fino (`ApifyCliente`) e um `ApifyColetor` atrás da interface `Coletor`. O serviço `coletar_lote` grava os posts de um `LoteColeta` e enfileira a extração, como antes. O worker cria os lotes na manutenção de 5 em 5 minutos (`agendar_lotes`): um por horário configurado e um imediato para perfis nunca coletados. Extração, reconciliação, API e front não mudam.

**Tech Stack:** Python 3.12, SQLAlchemy 2 + Alembic, Postgres 16, pytest + testcontainers, urllib (stdlib) para HTTP, Typer.

**Spec:** `docs/superpowers/specs/2026-10-22-fonte-apify-design.md`

## Global Constraints

- Actor `apify/instagram-post-scraper`, id padrão `nH2AHrwxeTRJoN5hX` (`APIFY_ACTOR_ID`).
- Toda execução envia `dataDetailLevel: "basicData"` e `skipPinnedPosts: true`.
- Lote agendado: `resultsLimit` 20; lote de novos: janela `"30 days"`, `resultsLimit` 50; no máximo 50 perfis por execução.
- `HORARIOS_COLETA` padrão `08:00,18:00`, fuso America/Sao_Paulo.
- `APIFY_PRECO_POR_POST` padrão `0.0017`; `custo_estimado = posts × preço`.
- Janela do lote agendado: horas desde o `concluido_em` do último lote agendado concluído + 1 h, arredondado para cima; sem lote anterior, `"30 days"`.
- 401, 402, 403 da Apify → `ApifyRecusou`, erro definitivo (sem retentativa). `FAILED`, `TIMED-OUT`, `ABORTED` ou mais de 15 min → `ExecucaoFalhou` (retentativa).
- `APIFY_TOKEN` só por variável de ambiente; nunca em código, teste, fixture ou commit.
- Comandos de teste a partir de `backend/`: `uv run pytest -W error -q`; saída limpa.
- Commits terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. `ownerUsername` com maiúsculas, ou o mesmo post (collab) devolvido para dois perfis do lote: grava uma vez, sem quebrar (Task 4, Task 5).
2. Item sem `timestamp` ou com `timestamp` inválido: o item é descartado com WARNING e o lote continua (Task 4).
3. Nenhum perfil acompanhado: nenhum lote é criado e nenhuma chamada à Apify é feita (Task 6).
4. Worker reiniciado várias vezes dentro do mesmo horário: continua um único lote agendado por horário (Task 6).
5. Perfil removido de todos os grupos entre a criação do lote e a execução: o lote ainda o coleta sem erro (Task 5).

---

## Estrutura de arquivos

```
backend/src/agenda/coleta/base.py       # PostColetado, ResultadoLote, Coletor, FakeColetor, PerfilPrivado/Inexistente
backend/src/agenda/coleta/apify.py      # ApifyCliente, ApifyColetor, ApifyRecusou, ExecucaoFalhou
backend/src/agenda/coleta/servico.py    # coletar_lote, agendar_lotes, janela_agendada, baixar_url
backend/src/agenda/models.py            # LoteColeta (sai ContaColeta e Perfil.proxima_coleta_em)
backend/migrations/versions/0004_remove_scraper_proprio.py
backend/migrations/versions/0005_lotes_coleta.py
backend/tests/fixtures/apify/           # respostas reais gravadas + README com as descobertas
docs/historico/scraper-instaloader.md
```

---

### Task 1: Execução real e fixtures da Apify

**Files:**
- Create: `backend/tests/fixtures/apify/README.md`, `backend/tests/fixtures/apify/*.json`
- Create (fora do repositório, descartável): script de sonda no scratchpad do executor

**Interfaces:**
- Produces: fixtures JSON com a resposta crua da API (lista de itens do dataset) e um README com duas respostas que as Tasks 4 e 6 consomem: **(a)** `onlyPostsNewerThan` aceita horas (`"12 hours"`)? **(b)** qual campo do item identifica a entrada de origem (por exemplo `inputUrl`), ou "nenhum".

- [ ] **Step 1:** Ler o token de `/Users/ebetcel/orca/projects/mestrado-app/backend/.env` (`APIFY_TOKEN`) sem imprimir o valor.
- [ ] **Step 2:** Uma execução com `username=["festivalmada", "jazznobardenazare", "perfil-que-nao-existe-agenda-xyz"]`, `resultsLimit=3`, `skipPinnedPosts=true`, `dataDetailLevel="basicData"` e `onlyPostsNewerThan="30 days"`, pela rota síncrona `run-sync-get-dataset-items`. Salvar a resposta em `fixtures/apify/lote_misto.json`.
- [ ] **Step 3:** Uma execução com `onlyPostsNewerThan="12 hours"` e um perfil. Registrar se a API aceitou (sem erro de validação) e se só vieram posts das últimas 12 h. Salvar em `fixtures/apify/janela_horas.json`, mesmo que venha vazio.
- [ ] **Step 4:** Garantir que as fixtures cubram imagem, carrossel (`Sidecar`), vídeo, legenda vazia ou nula e item com `error`. Se faltar algum tipo, uma terceira execução com um perfil que o tenha (até 3 posts). Remover das fixtures qualquer token ou cabeçalho; URLs de CDN podem ficar.
- [ ] **Step 5:** Escrever o README: data, perfis, entradas usadas, custo aproximado, respostas (a) e (b), e o texto exato das mensagens de `error` vistas (para a Task 4 classificar privado e inexistente).
- [ ] **Step 6:** Commit `test: fixtures reais da Apify`.

### Task 2: Remover o scraper próprio e registrar o histórico

**Files:**
- Create: `docs/historico/scraper-instaloader.md`, `backend/migrations/versions/0004_remove_scraper_proprio.py`
- Delete: `backend/src/agenda/coleta/instaloader_coletor.py`, `backend/src/agenda/coleta/pool.py`, `backend/tests/coleta/test_pool.py`, `backend/tests/coleta/test_instaloader_parser.py`, `backend/tests/fixtures/ig/`
- Modify: `coleta/base.py`, `coleta/servico.py`, `models.py`, `config.py`, `pipeline.py`, `worker.py`, `jobs.py`, `cli.py`, `api/grupos.py`, `pyproject.toml`, `uv.lock`, `.env.example`, `tests/coleta/test_servico.py`, `tests/test_pipeline.py`, `tests/test_cli.py`, `tests/test_jobs.py`
- Test: `backend/tests/test_migracao_0004.py`

**Interfaces:**
- Produces: `coleta/base.py` com só `PerfilPrivado` e `PerfilInexistente` (as Tasks 4 e 5 reescrevem o resto); `Dependencias` sem `coletor` e sem `intervalo_coleta_horas`; `HANDLERS` sem `coletar_perfil`; `Perfil` sem `proxima_coleta_em`; nenhum modelo `ContaColeta`.

- [ ] **Step 1:** Escrever `docs/historico/scraper-instaloader.md` a partir do código ainda presente, cobrindo os itens da spec seção 3 (arquitetura, coleta incremental, bloqueios, formatos de nó, motivo da remoção, commit `d926d8f`).
- [ ] **Step 2:** Teste `test_migracao_0004.py::test_0004_remove_contas_proxima_e_jobs_de_coleta`: com o banco em `0003`, inserir uma conta de coleta, um perfil `inexistente` com `ultima_coleta_em` nulo, um perfil `inexistente` já coletado e dois jobs (`coletar_perfil` e `extrair_post`); aplicar `0004`; afirmar que a tabela `contas_coleta` e a coluna `perfis.proxima_coleta_em` não existem, que só o job `extrair_post` restou, que o perfil `inexistente` nunca coletado virou `ativo` e que o já coletado continua `inexistente`. Mais `test_0004_downgrade` (volta a `0003` sem erro).
- [ ] **Step 3:** Rodar `uv run pytest tests/test_migracao_0004.py -v`. Esperado: FAIL.
- [ ] **Step 4:** Escrever `0004`: `DROP TABLE contas_coleta`, `DROP COLUMN perfis.proxima_coleta_em`, `DELETE FROM jobs WHERE tipo = 'coletar_perfil'`, `UPDATE perfis SET status='ativo' WHERE status='inexistente' AND ultima_coleta_em IS NULL`. O downgrade recria a tabela e a coluna vazias, como em `0001`.
- [ ] **Step 5:** Remover o código: os arquivos listados em Delete; `ContaColeta` e `Perfil.proxima_coleta_em` em `models.py`; `chave_sessao`, `intervalo_coleta_horas` e `limite_requisicoes_conta_hora` em `Settings` e `.env.example`; `coletar_perfil`, `agendar_coletas` e `MAX_FIXADOS` em `servico.py` (fica `baixar_url`); o handler `coletar_perfil`, `Dependencias.coletor` e `intervalo_coleta_horas` em `pipeline.py`; o ramo `SemContasDisponiveis`, `_adiar_proxima_coleta`, `ESPERA_SEM_CONTAS` e a chamada a `agendar_coletas` em `worker.py`; `jobs.adiar` e seu teste; em `cli.py` os comandos `conta-adicionar` e `coletar`, `_validar_chave_sessao`, o coletor no `build_deps`, a coluna de próxima coleta de `perfil-listar` e o `proxima_coleta_em` de `perfil-adicionar`; em `TIPOS_PADRAO`, só `extrair_post`; em `api/grupos.py`, o `reativar_ou_enfileirar` de `coletar_perfil` (o lote de novos da Task 6 assume esse papel); `instaloader` e `cryptography` em `pyproject.toml` (`uv lock`). Apagar ou ajustar os testes que exercitavam essas partes.
- [ ] **Step 6:** `grep -rniE "instaloader|ContaColeta|contas_coleta|chave_sessao|SemContasDisponiveis|ContaBloqueada|MAX_FIXADOS|proxima_coleta|coletar_perfil|fixado" backend/src backend/tests` não encontra nada fora da migração `0004`, das migrações antigas e de `test_migracao_0004.py`.
- [ ] **Step 7:** Rodar a suíte inteira. Esperado: PASS, saída limpa.
- [ ] **Step 8:** Commit `refactor: remove o scraper próprio (instaloader e contas)`.

### Task 3: Cliente REST da Apify

**Files:**
- Create: `backend/src/agenda/coleta/apify.py` (parte do cliente)
- Test: `backend/tests/coleta/test_apify_cliente.py`

**Interfaces:**
- Produces:
  - `Transporte = Callable[[str, str, dict | None], tuple[int, Any]]` (método, URL, corpo JSON) → (status HTTP, JSON decodificado). Padrão: `transporte_urllib` (urllib, timeout 60 s).
  - `ApifyCliente(token: str, actor_id: str, *, transporte: Transporte = transporte_urllib, relogio=time.monotonic)`.
  - `iniciar(entrada: dict) -> str` (id da execução); `aguardar(run_id: str, *, timeout: timedelta = timedelta(minutes=15)) -> str` (id do dataset); `itens(dataset_id: str) -> list[dict]`.
  - Exceções `ApifyRecusou(Exception)` e `ExecucaoFalhou(Exception)`.
- O token vai como cabeçalho `Authorization: Bearer <token>`, nunca na URL nem nas mensagens de erro.

- [ ] **Step 1:** Testes com um transporte falso que registra as chamadas: `test_iniciar_posta_no_actor_e_devolve_run_id`; `test_aguardar_ate_sucesso_devolve_dataset` (RUNNING, RUNNING, SUCCEEDED); `test_aguardar_falha_levanta_execucao_falhou` (parametrizado em FAILED, TIMED-OUT, ABORTED); `test_aguardar_passa_do_timeout_levanta_execucao_falhou` (relógio falso); `test_itens_pagina_ate_acabar` (páginas de 1000 com `offset`); `test_recusa_401_402_403_levanta_apify_recusou` (parametrizado); `test_5xx_propaga_erro_de_transporte`; `test_token_nunca_aparece_na_url_nem_na_mensagem`.
- [ ] **Step 2:** `uv run pytest tests/coleta/test_apify_cliente.py -v`. Esperado: FAIL.
- [ ] **Step 3:** Implementar. Endpoints: `POST /v2/acts/{actor_id}/runs`, `GET /v2/actor-runs/{run_id}?waitForFinish=60`, `GET /v2/datasets/{dataset_id}/items?format=json&clean=true&offset=N&limit=1000`, base `https://api.apify.com`.
- [ ] **Step 4:** Rodar os testes. Esperado: PASS.
- [ ] **Step 5:** Commit `feat: cliente REST da Apify`.

### Task 4: ApifyColetor e tipos da coleta

**Files:**
- Modify: `backend/src/agenda/coleta/base.py`, `backend/src/agenda/coleta/apify.py`
- Test: `backend/tests/coleta/test_apify_coletor.py`

**Interfaces:**
- Consumes: `ApifyCliente` (Task 3); fixtures e README da Task 1.
- Produces:
  - `PostColetado(shortcode: str, legenda: str, publicado_em: datetime, urls_imagens: list[str], perfil: str)` — `perfil` é o username pedido, em minúsculas.
  - `ResultadoLote(posts: list[PostColetado], erros: dict[str, str], run_ids: list[str])`.
  - `Coletor` (Protocol): `coletar(usernames: list[str], *, janela: str, limite: int) -> ResultadoLote`.
  - `FakeColetor(posts: list[PostColetado], erros: dict[str, str] | None = None)`: devolve só os posts e erros dos usernames pedidos e registra cada chamada em `self.chamadas`.
  - `ApifyColetor(cliente: ApifyCliente)` e a função pura `converter_itens(itens: list[dict], usernames: list[str]) -> ResultadoLote`.
  - `classificar_erro(mensagem: str) -> Literal["privado", "inexistente"] | None`, com os padrões tirados do README da Task 1.

- [ ] **Step 1:** Testes a partir das fixtures: `test_converte_imagem_carrossel_e_video` (carrossel com todas as `images`; vídeo e `images` vazio caem para `[displayUrl]`); `test_legenda_nula_vira_vazia`; `test_timestamp_vira_datetime_utc`; `test_item_sem_timestamp_e_descartado_com_warning` (caplog); `test_item_com_error_vai_para_erros_pelo_username`; `test_atribui_ao_perfil_pedido` (pela regra que o README da Task 1 definiu: campo de entrada ou `ownerUsername`); `test_owner_com_maiusculas_casa_com_pedido`; `test_item_de_dono_nao_pedido_e_descartado`; `test_mesmo_shortcode_duas_vezes_fica_uma`; `test_classificar_erro` (privado, inexistente, desconhecido → None); `test_coletor_envia_entrada_fixa` (com cliente falso: `username`, `onlyPostsNewerThan`, `resultsLimit`, `skipPinnedPosts=True`, `dataDetailLevel="basicData"`) e `test_coletor_devolve_run_ids`.
- [ ] **Step 2:** `uv run pytest tests/coleta/test_apify_coletor.py -v`. Esperado: FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar os testes. Esperado: PASS.
- [ ] **Step 5:** Commit `feat: ApifyColetor e tipos da coleta em lote`.

### Task 5: Lotes de coleta e gravação

**Files:**
- Create: `backend/migrations/versions/0005_lotes_coleta.py`
- Modify: `models.py`, `coleta/servico.py`, `pipeline.py`, `config.py`, `cli.py` (`build_deps`), `.env.example`
- Test: `backend/tests/coleta/test_coletar_lote.py`, `backend/tests/test_models.py`

**Interfaces:**
- Consumes: `Coletor`, `FakeColetor`, `ResultadoLote`, `classificar_erro`, `ApifyColetor`, `ApifyCliente` (Tasks 3–4).
- Produces:
  - Modelo `LoteColeta` com as colunas da spec 4.3. `tipo` ∈ {agendado, novos}; `status` ∈ {pendente, executando, concluido, erro} (padrão pendente); índice único parcial em `horario` onde `tipo = 'agendado'`.
  - `coletar_lote(s, lote_id: int, coletor: Coletor, storage: Storage, *, agora: datetime, baixar=baixar_url, preco_por_post: Decimal) -> int` (posts novos).
  - Handler `coletar_lote` em `HANDLERS` (payload `{"lote_id": id}`); `Dependencias.coletor: Coletor` volta, com `preco_por_post: Decimal`.
  - `Settings`: `apify_token: str = ""`, `apify_actor_id: str = "nH2AHrwxeTRJoN5hX"`, `apify_preco_por_post: Decimal = Decimal("0.0017")`. `build_deps` falha com mensagem clara se `apify_token` estiver vazio.

- [ ] **Step 1:** Testes com `FakeColetor` e `MemoriaStorage`: `test_grava_posts_novos_baixa_imagens_e_enfileira_extracao`; `test_shortcode_existente_e_ignorado`; `test_quebra_em_execucoes_de_50` (120 perfis → 3 chamadas, 50/50/20); `test_erro_privado_e_inexistente_mudam_status`; `test_erro_desconhecido_mantem_ativo_e_registra_warning`; `test_imagem_que_falha_e_pulada_e_post_salvo_com_as_outras`; `test_ultima_coleta_atualizada_so_para_perfis_sem_erro`; `test_lote_registra_posts_posts_novos_custo_run_ids_e_concluido` (posts = devolvidos, inclusive repetidos; custo = posts × 0.0017); `test_perfil_fora_de_grupos_ainda_e_coletado`; `test_lote_concluido_nao_e_reprocessado`. Em `test_models.py`: `test_lote_agendado_unico_por_horario`.
- [ ] **Step 2:** `uv run pytest tests/coleta/test_coletar_lote.py tests/test_models.py -v`. Esperado: FAIL.
- [ ] **Step 3:** Implementar o modelo, a migração `0005`, `coletar_lote`, o handler e `build_deps` (`ApifyColetor(ApifyCliente(settings.apify_token, settings.apify_actor_id))`). O lote passa a `executando` ao começar; `concluido` ao fim. Se `coletar` levantar `ApifyRecusou` ou `ExecucaoFalhou`, a exceção propaga (o worker decide; Task 6).
- [ ] **Step 4:** Rodar os testes. Esperado: PASS.
- [ ] **Step 5:** Commit `feat: lotes de coleta via Apify`.

### Task 6: Agendamento dos lotes e worker

**Files:**
- Modify: `coleta/servico.py`, `worker.py`, `config.py`, `.env.example`, `cli.py` (`TIPOS_PADRAO`)
- Test: `backend/tests/coleta/test_agendar_lotes.py`, `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: `LoteColeta`, handler `coletar_lote` (Task 5); `ApifyRecusou` (Task 3).
- Produces:
  - `Settings.horarios_coleta: str = "08:00,18:00"`.
  - `ultimo_horario(agora: datetime, horarios: list[time]) -> datetime` (o horário configurado mais recente ≤ agora, em America/Sao_Paulo, como timestamptz).
  - `janela_agendada(ultimo_concluido: datetime | None, agora: datetime) -> str`.
  - `agendar_lotes(s, agora: datetime) -> list[int]` (ids dos lotes criados).
  - `TIPOS_PADRAO = "coletar_lote,extrair_post"`; a manutenção do worker chama `agendar_lotes` quando `coletar_lote` está nos tipos.
  - `ApifyRecusou` no worker → `falhar_definitivo` + lote `erro` + log ERROR; outras exceções num job `coletar_lote` esgotado → lote `erro`.

- [ ] **Step 1:** Testes: `test_ultimo_horario_manha_tarde_e_madrugada` (07:00 SP → 18:00 da véspera; 09:00 → 08:00; 19:00 → 18:00); `test_um_lote_por_horario_mesmo_com_varias_passadas`; `test_pausa_longa_gera_um_so_lote_com_janela_cobrindo_tudo`; `test_janela_agendada` (concluído há 10 h 20 min → `"12 hours"`; sem anterior → `"30 days"`; ou o formato de data, se o README da Task 1 disser que horas não são aceitas); `test_lote_agendado_so_com_perfis_ja_coletados_e_acompanhados`; `test_lote_de_novos_imediato_com_30_dias_e_limite_50`; `test_nao_cria_segundo_lote_de_novos_enquanto_um_esta_pendente`; `test_sem_perfis_acompanhados_nao_cria_lote`. Em `test_pipeline.py`: `test_fluxo_do_lote_a_reconciliacao` (perfil novo → lote de novos → post → evento, via `rodar_worker(uma_vez=True)`); `test_apify_recusou_e_definitivo`; `test_execucao_falhou_repete_e_marca_lote_erro_ao_esgotar`.
- [ ] **Step 2:** `uv run pytest tests/coleta/test_agendar_lotes.py tests/test_pipeline.py -v`. Esperado: FAIL.
- [ ] **Step 3:** Implementar. O lote agendado usa o índice único em `horario` para garantir um por horário (`ON CONFLICT DO NOTHING`); o job tem chave `lote:{id}`.
- [ ] **Step 4:** Rodar a suíte inteira. Esperado: PASS.
- [ ] **Step 5:** Commit `feat: agendamento dos lotes de coleta`.

### Task 7: CLI, documentação e verificação real

**Files:**
- Modify: `cli.py`, `backend/README.md`, `web/README.md`, `.env.example`, `.claude/skills/agenda-servicos/SKILL.md`
- Test: `backend/tests/test_cli.py`

**Interfaces:**
- Consumes: `LoteColeta`, `janela_agendada`, `reativar_ou_enfileirar` (Tasks 5–6).
- Produces: `agenda coletar [--perfil X]` (cria um lote imediato e enfileira; perfil nunca coletado usa `"30 days"`/50, os demais a janela agendada/20; sem `--perfil`, todos os acompanhados); `agenda lotes [--ultimos N]` (padrão 10; colunas: id, tipo, criado, status, perfis, posts, novos, custo; linha final com o total de `custo_estimado` do mês corrente em São Paulo).

- [ ] **Step 1:** Testes: `test_coletar_perfil_novo_cria_lote_de_30_dias`; `test_coletar_sem_perfil_inclui_todos_os_acompanhados`; `test_coletar_perfil_desconhecido_falha_com_mensagem`; `test_lotes_lista_e_soma_o_mes`.
- [ ] **Step 2:** `uv run pytest tests/test_cli.py -v`. Esperado: FAIL.
- [ ] **Step 3:** Implementar os comandos e atualizar os documentos: tirar conta do Instagram, `CHAVE_SESSAO` e `instaloader` dos READMEs, do `.env.example` e da skill; incluir `APIFY_TOKEN`, `HORARIOS_COLETA`, `agenda lotes` e o fluxo novo.
- [ ] **Step 4:** Rodar a suíte inteira. Esperado: PASS.
- [ ] **Step 5:** Verificação real, com o `.env` do checkout principal copiado temporariamente para `backend/.env` da worktree e banco de teste próprio (`createdb agenda_apify` no Postgres local, `DATABASE_URL` apontando para ele, `alembic upgrade head`): `agenda perfil-adicionar jazznobardenazare`, `agenda coletar --perfil jazznobardenazare`, `agenda worker --uma-vez`, `agenda lotes`. Esperado: um lote `concluido` com posts e custo, posts gravados e jobs de extração enfileirados. Apagar o `.env` copiado e o banco `agenda_apify` ao final.
- [ ] **Step 6:** Commit `feat: CLI de lotes e documentação da coleta via Apify`.
