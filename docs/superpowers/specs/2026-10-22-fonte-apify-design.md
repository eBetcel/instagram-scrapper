# Fonte de dados via Apify — Design

**Data:** 2026-10-22
**Status:** aguardando revisão
**Substitui:** a seção 3.3 (Coleta) da spec `2026-10-09-agenda-cultural-instagram-design.md`.

## 1. Objetivo e contexto

O scraper próprio (instaloader com pool de contas do Instagram) ficou inviável: a conta de coleta passou a receber `feedback_required` em toda consulta de posts, embora funcione normalmente no app. A coleta passa a usar uma API externa, o actor `apify/instagram-post-scraper` da Apify, que dispensa contas e proxies.

**O que o usuário pediu:**
- Trocar o scraper próprio pela API da Apify.
- Gastar o mínimo com a API, trazendo só posts novos, com coleta agendada.
- Remover todo o código do scraper local.
- Guardar um `.md` com a descrição técnica do scraper antigo, só como registro histórico.

**Critérios de sucesso:**
- Duas vezes por dia, os posts novos de todos os perfis acompanhados chegam ao pipeline (extração e reconciliação) sem intervenção.
- Um @ nunca coletado, adicionado a um grupo, tem seus posts dos últimos 30 dias coletados em minutos.
- Cada post é cobrado o mínimo de vezes possível. Repetições, quando houver, são descartadas pela deduplicação por `shortcode`.
- O código não tem mais nenhuma referência a instaloader, contas de coleta ou sessões cifradas.
- O gasto de cada coleta fica registrado e consultável.

## 2. Decisões

| Tema | Decisão |
|---|---|
| Fonte | Actor `apify/instagram-post-scraper` (id `nH2AHrwxeTRJoN5hX`), cobrado por post retornado (~US$ 0,0017 no plano Free) |
| Frequência | Duas coletas por dia, horários configuráveis (padrão `08:00,18:00`, America/Sao_Paulo) |
| Forma | Um lote por horário com todos os perfis já coletados, em execuções de até 50 perfis cada |
| Perfil novo | Lote imediato (verificação a cada 5 min), janela de 30 dias, até 50 posts |
| Teto de gasto | Nenhum no sistema; o controle é o limite de gasto da conta Apify. O sistema só registra o gasto estimado |
| Chamada à API | REST assíncrona da Apify (iniciar execução → acompanhar status → baixar itens), sem SDK |
| Scraper antigo | Removido do código; descrito em `docs/historico/scraper-instaloader.md` |

## 3. O que sai

- **Arquivos:** `backend/src/agenda/coleta/instaloader_coletor.py` e `backend/src/agenda/coleta/pool.py`.
- **`coleta/base.py`:** `ContaBloqueada`, `SemContasDisponiveis`, `MAX_FIXADOS` e o campo `PostColetado.fixado`. O `skipPinnedPosts` da Apify substitui o tratamento de posts fixados.
- **Modelo e banco:** o modelo `ContaColeta` e a coluna `Perfil.proxima_coleta_em`. A migração `0004` apaga a tabela `contas_coleta`, a coluna `perfis.proxima_coleta_em` e todos os jobs do tipo `coletar_perfil`.
- **Configuração:** `CHAVE_SESSAO` e `LIMITE_REQUISICOES_CONTA_HORA` (Settings, `.env.example`), além da validação da chave em `build_deps`. `INTERVALO_COLETA_HORAS` também sai, substituída por `HORARIOS_COLETA`.
- **CLI:** o comando `conta-adicionar`. `perfil-listar` deixa de mostrar a próxima coleta.
- **Worker:** o tratamento de `SemContasDisponiveis`, o handler `coletar_perfil`, o ajuste de `proxima_coleta_em` quando a coleta esgota as tentativas, e `jobs.adiar` se ficar sem uso.
- **Dependências:** `instaloader` e `cryptography` (usada só pelas sessões).
- **Testes e fixtures:** `tests/coleta/test_pool.py`, `tests/coleta/test_instaloader_parser.py`, `tests/fixtures/ig/` e as partes de `test_servico.py`, `test_pipeline.py`, `test_cli.py` e `tests/api/conftest.py` que dependem do scraper antigo.
- **Documentação atual:** `backend/README.md`, `web/README.md`, `.env.example` e a skill `.claude/skills/agenda-servicos`. As specs e planos antigos ficam como estão, como histórico.

**Registro histórico (`docs/historico/scraper-instaloader.md`):** arquitetura (interface `Coletor`, `InstaloaderColetor`, `PoolContas` com janela por hora, sessões cifradas com Fernet), regras de coleta incremental (parada no primeiro `shortcode` conhecido deste perfil, os 3 primeiros posts isentos por causa dos fixados, posts collab pulados), tratamento de bloqueios (`ContaBloqueada`, `SemContasDisponiveis`, adiamento sem gastar tentativa), formatos de nó do instaloader (anônimo e logado), o motivo da remoção e o hash do último commit com o código (`d926d8f`).

## 4. O que entra

### 4.1 Cliente Apify (`coleta/apify.py`)

`ApifyCliente(token: str, actor_id: str, *, transporte=...)`, com o transporte HTTP injetável para os testes:
- `iniciar(entrada: dict) -> str`: `POST /v2/acts/{actor_id}/runs` e devolve o id da execução.
- `aguardar(run_id: str, *, timeout: timedelta) -> Execucao`: consulta `GET /v2/actor-runs/{run_id}` (com `waitForFinish`) até um estado final. `SUCCEEDED` devolve o `defaultDatasetId`. `FAILED`, `TIMED-OUT` e `ABORTED` levantam `ExecucaoFalhou`.
- `itens(dataset_id: str) -> list[dict]`: `GET /v2/datasets/{dataset_id}/items` (paginado).
- Erros HTTP 401, 402 e 403 levantam `ApifyRecusou` (token inválido ou limite da conta). 5xx e erros de rede levantam a exceção de transporte original.

`ApifyColetor(cliente)` implementa a nova interface `Coletor`:

```python
def coletar(self, usernames: list[str], *, janela: str, limite: int) -> ResultadoLote: ...
```

- Monta a entrada com `username=usernames`, `onlyPostsNewerThan=janela`, `resultsLimit=limite`, `skipPinnedPosts=True` e `dataDetailLevel="basicData"`.
- Devolve `ResultadoLote(posts: list[PostColetado], erros: dict[str, str], run_ids: list[str])`.
- Itens com a chave `error` vão para `erros`, indexados pelo username pedido. Os demais viram `PostColetado`.

`PostColetado` passa a ter: `shortcode` (de `shortCode`), `legenda` (`caption` ou `""`), `publicado_em` (de `timestamp`, tz-aware UTC), `urls_imagens` (`images` ou, se vazio, `[displayUrl]`) e `perfil` (o username pedido a que o item pertence).

**Atribuição do item ao perfil pedido:** se o item informar de qual entrada veio (um campo como `inputUrl`), usa-se essa entrada. Senão, usa-se `ownerUsername` em minúsculas quando ele estiver entre os perfis do lote. Um item que não se encaixe em nenhum dos dois casos é descartado com log WARNING. A primeira execução real (seção 6) confirma qual dos dois casos vale.

### 4.2 Gravação (`coleta/servico.py`)

`coletar_lote(s, lote_id, coletor, storage, *, agora, baixar=baixar_url) -> int` (devolve quantos posts novos foram salvos):
- Lê os perfis e a janela do `LoteColeta`, chama `coletor.coletar` em pedaços de até 50 perfis e processa o resultado.
- **Por post:** ignora o `shortcode` que já existe (de qualquer perfil); baixa as imagens; grava o post (`ON CONFLICT (shortcode) DO NOTHING`), salva as imagens em `posts/{shortcode}/{n}.jpg` e enfileira `extrair_post`, como hoje.
- **Imagem que falha ao baixar:** é pulada com log WARNING. O post é salvo com as imagens que baixaram, possivelmente nenhuma, e a extração usa só a legenda.
- **Erros por perfil:** mensagem que indique perfil privado → `status = privado`; inexistente ou não encontrado → `status = inexistente`; qualquer outra → log WARNING, perfil continua `ativo`. Os padrões de mensagem vêm das fixtures reais (seção 6).
- **Ao final:** `ultima_coleta_em = agora` para cada perfil do lote que não teve erro, e o `LoteColeta` recebe `concluido_em`, `posts`, `custo_estimado` e `run_ids`.

### 4.3 Registro de lotes (tabela `lotes_coleta`)

| Coluna | Tipo | Observação |
|---|---|---|
| `id` | int PK | |
| `tipo` | `agendado` \| `novos` | |
| `horario` | timestamptz \| null | horário agendado a que o lote corresponde; único entre lotes `agendado` |
| `janela` | text | valor enviado em `onlyPostsNewerThan` |
| `limite` | int | `resultsLimit` por perfil |
| `perfis` | text[] | usernames do lote |
| `status` | `pendente` \| `executando` \| `concluido` \| `erro` | |
| `run_ids` | text[] | ids das execuções na Apify |
| `posts` | int | posts devolvidos pela Apify, novos ou repetidos (é o que se paga) |
| `posts_novos` | int | posts gravados |
| `custo_estimado` | numeric(10,4) | `posts × APIFY_PRECO_POR_POST` |
| `criado_em`, `concluido_em` | timestamptz | |
| `erro_msg` | text \| null | |

### 4.4 Agendamento

- **Configuração:** `HORARIOS_COLETA` (padrão `08:00,18:00`) em America/Sao_Paulo, `APIFY_TOKEN`, `APIFY_ACTOR_ID` (padrão `nH2AHrwxeTRJoN5hX`) e `APIFY_PRECO_POR_POST` (padrão `0.0017`).
- **`agendar_lotes(s, agora) -> list[int]`** roda na manutenção do worker, a cada 5 minutos:
  - **Lote agendado:** encontra o horário configurado mais recente que já passou. Se não existir `LoteColeta` agendado para ele, cria um (`tipo=agendado`, `limite=20`) com todos os perfis acompanhados já coletados (`ativo`, `ultima_coleta_em` preenchido, em algum grupo ou `fixo`). Também enfileira o job `coletar_lote`. Horários que passaram enquanto o worker estava parado não são recuperados um a um: só o mais recente gera lote, e a janela cobre todo o intervalo.
  - **Lote de novos:** se houver perfis acompanhados nunca coletados (`ultima_coleta_em` nulo) e nenhum lote `novos` pendente ou em execução, cria um lote `novos` com eles (`janela="30 days"`, `limite=50`) e enfileira o job.
- **Janela do lote agendado:** o tempo desde o `concluido_em` do último lote agendado concluído, mais 1 hora de folga, arredondado para cima em horas (`"13 hours"`). Se a Apify não aceitar horas (verificado na seção 6), usa-se a data em São Paulo desse `concluido_em` (`YYYY-MM-DD`). Sem nenhum lote agendado concluído, usa-se `"30 days"`.
- Um job `coletar_lote` tem payload `{"lote_id": id}` e chave `lote:{id}`.
- Lotes `agendado` e `novos` nunca contêm o mesmo perfil, então podem rodar ao mesmo tempo.

### 4.5 Ponto de entrada na CLI

- `agenda coletar [--perfil X]` passa a criar um lote imediato: só com o perfil indicado ou, sem `--perfil`, com todos os perfis acompanhados. A janela é a do próximo lote agendado, ou `"30 days"` para um perfil nunca coletado.
- `agenda lotes [--ultimos N]` lista os lotes com status, posts, posts novos e custo estimado, além do total gasto no mês corrente.

## 5. Tratamento de erros

| Situação | Comportamento |
|---|---|
| Item com `error` | O perfil é marcado `privado`/`inexistente` ou recebe log WARNING; os outros perfis do lote seguem |
| `ExecucaoFalhou`, 5xx, erro de rede | O job repete com o backoff existente; ao esgotar, o lote fica `erro`. A janela da próxima coleta parte do último lote concluído, então nada se perde |
| `ApifyRecusou` (401/402/403) | Erro definitivo, sem repetir, log ERROR, lote `erro`. É como o limite de gasto da conta Apify pausa a coleta |
| Imagem que não baixa | Pulada com WARNING; o post é salvo com o que baixou |
| Worker parado por horas | Ao voltar, um único lote agendado cobre todo o intervalo |
| Execução da Apify passa de 15 min | `aguardar` levanta `ExecucaoFalhou` (timeout) e o job repete |

## 6. Testes

- **Primeira execução real** (manual, com `APIFY_TOKEN`), custo de centavos: 2 perfis acompanhados, com `resultsLimit=3`. Grava as respostas brutas como fixtures em `backend/tests/fixtures/apify/`, cobrindo imagem, vídeo, carrossel e legenda vazia, mais um perfil inexistente para o item com `error`. A mesma execução responde se `onlyPostsNewerThan` aceita horas e se cada item informa a entrada de origem.
- **Conversão dos itens** (`ApifyColetor`): a partir das fixtures, cobrindo os tipos de post, a legenda nula, `images` vazio caindo para `displayUrl`, o item com erro e a atribuição ao perfil pedido.
- **`ApifyCliente`:** com transporte HTTP falso, cobrindo sucesso, `FAILED`, timeout, 401, 402 e a paginação de itens.
- **`coletar_lote`:** com coletor falso e `MemoriaStorage`, cobrindo deduplicação, perfil privado e inexistente, imagem que falha, divisão em pedaços de 50, atualização de `ultima_coleta_em` e registro do lote.
- **`agendar_lotes`:** os dois horários em São Paulo, um lote por horário mesmo com várias passadas, a retomada depois de uma pausa (um só lote, janela cobrindo tudo), o lote de novos imediato e o não-duplicado, e o cálculo da janela.
- **Migração `0004`:** sobe e desce, e apaga os jobs `coletar_perfil`.
- **Ponta a ponta:** o fluxo do `coletar_lote` à reconciliação, com coletor falso, através do worker.

## 7. Transição

- Posts, eventos, grupos e perfis existentes ficam intactos. Somem só a tabela `contas_coleta` (com a sessão de `vocetemdados`), a coluna `proxima_coleta_em` e os jobs `coletar_perfil` pendentes.
- O worker de coleta (`com.agenda.worker`) só volta a rodar depois da implementação e com o `APIFY_TOKEN` no `.env`.
- Perfis marcados `inexistente` durante o bloqueio do instaloader (`ebetcel12`, `fica.bar`) podem ser falsos positivos. A primeira coleta Apify os reavalia: a migração os devolve a `ativo` com `ultima_coleta_em` nulo, para entrarem no lote de novos.

## 8. Fora de escopo

- Frequência de coleta diferente por perfil.
- Agendamento na própria Apify com webhook (exige API pública).
- Teto de gasto no sistema.
- Stories e Reels.
