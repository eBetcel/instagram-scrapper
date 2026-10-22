# Scraper próprio do Instagram (instaloader) — registro histórico

Este documento descreve o coletor de posts que a agenda usou até outubro de 2026,
antes da troca pela API da Apify (spec `docs/superpowers/specs/2026-10-22-fonte-apify-design.md`).
O código foi removido; aqui fica só a descrição técnica, para consulta.

**Último commit com o código:** `d926d8f` (`feat(web): período "Próximos" (60 dias) na agenda`).

## Como recuperar o código

```sh
git show d926d8f:backend/src/agenda/coleta/instaloader_coletor.py
git show d926d8f:backend/src/agenda/coleta/pool.py
git show d926d8f:backend/src/agenda/coleta/base.py
git show d926d8f:backend/src/agenda/coleta/servico.py
git show d926d8f:backend/src/agenda/worker.py
git show d926d8f:backend/src/agenda/cli.py
git show d926d8f:backend/tests/coleta/test_instaloader_parser.py
git show d926d8f:backend/tests/coleta/test_pool.py
git ls-tree -r d926d8f backend/tests/fixtures/ig   # fixtures sintéticas dos nós
```

Para restaurar a árvore inteira daquele momento: `git worktree add ../scraper-antigo d926d8f`.

## Arquitetura

```
worker (manutenção a cada 5 min) ── agendar_coletas ──> jobs coletar_perfil
worker ── tratar_coletar_perfil ──> servico.coletar_perfil(s, perfil_id, coletor, storage, ...)
                                        │
                                        └─ Coletor.posts_desde(username, desde)
                                              = InstaloaderColetor ── PoolContas (contas_coleta)
                                                                     └─ instaloader.Profile.get_posts()
```

- **Interface `Coletor`** (`coleta/base.py`): um `Protocol` com um único método,
  `posts_desde(username: str, desde: datetime | None) -> Iterable[PostColetado]`, que
  devolve os posts do perfil do mais novo para o mais antigo. `PostColetado` tinha
  `shortcode`, `legenda`, `publicado_em` (tz-aware, UTC), `urls_imagens` (vazia para vídeo
  sem capa) e `fixado`. O `FakeColetor` servia aos testes, com posts e erros por perfil.
- **`InstaloaderColetor`** (`coleta/instaloader_coletor.py`): a cada chamada pegava uma
  conta do pool, montava um `instaloader.Instaloader(quiet=True, max_connection_attempts=1)`,
  carregava a sessão da conta (`load_session`) e abria `Profile.from_username`. Perfil
  privado não seguido pela conta virava `PerfilPrivado`; `ProfileNotExistsException`
  virava `PerfilInexistente`. A fábrica de perfil era injetável, o que permitia testar
  sem rede.
- **`PoolContas`** (`coleta/pool.py`): contas de coleta na tabela `contas_coleta`
  (`usuario_ig`, `sessao_criptografada`, `status` ∈ ativa/bloqueada/desativada,
  `bloqueada_ate`, `ultimo_uso_em`, `usos_janela`, `janela_inicio`), compartilhadas entre
  workers. `obter()` escolhia, com `SELECT ... FOR UPDATE SKIP LOCKED`, a conta usável há
  mais tempo sem uso (`ultimo_uso_em` nulo primeiro). Cada conta tinha uma **janela de uma
  hora**: ao passar uma hora desde `janela_inicio`, a janela recomeçava com `usos_janela = 0`;
  uma conta com `usos_janela >= LIMITE_REQUISICOES_CONTA_HORA` (padrão 20) era pulada.
  Conta bloqueada cujo `bloqueada_ate` já passou voltava a `ativa` ao ser escolhida. Cada
  operação usava sessão curta própria com commit, e a conta devolvida era destacada
  (`expunge`) para sobreviver ao fechamento da sessão.
- **Sessões cifradas com Fernet:** o comando `agenda conta-adicionar USUARIO --sessao-arquivo X`
  lia o arquivo de sessão do instaloader (pickle de um dict de cookies, gerado por
  `instaloader --login X`), cifrava o JSON dos cookies com `cryptography.fernet.Fernet`
  usando `CHAVE_SESSAO` e gravava em `contas_coleta.sessao_criptografada`. O coletor
  decifrava na hora de usar. `build_deps` validava a chave Fernet já na partida do worker,
  para falhar cedo e não na primeira coleta.
- **Agendamento por perfil:** `perfis.proxima_coleta_em` marcava quando o perfil voltava a
  ser devido. `agendar_coletas` (chamado na manutenção do worker quando `coletar_perfil`
  estava entre os tipos) criava ou reativava um job `coletar_perfil` (chave `coletar:<id>`)
  para cada perfil `ativo` devido que estivesse em algum grupo ou fosse `fixo` (cadastrado
  pela CLI). Perfil nunca coletado rodava imediatamente; os demais recebiam jitter de até
  30 min. Depois de cada coleta, `proxima_coleta_em = agora + INTERVALO_COLETA_HORAS` (6 h).
  `agenda coletar [--perfil X]` adiantava a coleta manualmente, e adicionar um @ a um grupo
  pela API enfileirava `coletar_perfil` na hora.

## Coleta incremental

`servico.coletar_perfil` percorria o iterador do coletor e decidia quando parar:

- `desde` = `ultima_coleta_em` do perfil, ou 30 dias atrás na primeira coleta. Post anterior
  a `desde` nunca era salvo.
- **Parada no primeiro `shortcode` conhecido deste perfil:** ao encontrar um post já salvo
  pelo próprio perfil, a coleta parava (o resto já tinha sido visto). Também parava no
  primeiro post mais antigo que `desde`.
- **Os 3 primeiros posts isentos (`MAX_FIXADOS = 3`):** o Instagram mostra até 3 posts
  fixados no topo do perfil, fora da ordem cronológica, e o marcador de fixado nem sempre
  vem no nó. Por isso os 3 primeiros posts (e qualquer post com `fixado=True`) eram
  "âncoras": se fossem antigos ou já conhecidos, eram pulados em vez de encerrar a coleta.
  O próprio `InstaloaderColetor` aplicava a mesma regra para parar de paginar.
- **Posts collab pulados:** um post já salvo por **outro** perfil (colaboração) era só
  pulado, sem marcar ponto de parada; a atribuição a vários perfis ficou para depois.
- Cada post novo tinha as imagens baixadas antes do `INSERT` (falha de download não
  deixava post parcial), gravadas no S3 em `posts/<shortcode>/<n>.jpg`, e enfileirava
  `extrair_post`. O `INSERT ... ON CONFLICT (shortcode) DO NOTHING` tornava a coleta
  idempotente.
- `PerfilPrivado` e `PerfilInexistente` mudavam o `status` do perfil e encerravam a coleta
  sem erro. Ao fim, `ultima_coleta_em` e `proxima_coleta_em` eram atualizados.

## Tratamento de bloqueios

- **`ContaBloqueada`:** o coletor tratava como bloqueio `LoginRequiredException`,
  `TooManyRequestsException` e `ConnectionException` cuja mensagem contivesse `401`, `429`,
  `checkpoint` ou `please wait`. A conta era marcada `bloqueada` por 6 horas
  (`bloqueada_ate`) e a exceção propagava; o job falhava e era repetido com backoff normal,
  provavelmente com outra conta.
- **`SemContasDisponiveis(disponivel_em)`:** levantada pelo pool quando nenhuma conta
  servia. `disponivel_em` era o menor instante futuro em que alguma conta não desativada
  voltaria (fim de bloqueio ou fim da janela de uso cheia), ou `None` se não havia conta.
- **Adiamento sem gastar tentativa:** o worker capturava `SemContasDisponiveis` à parte e
  chamava `jobs.adiar`, que devolvia o job a `pendente` para `disponivel_em` (ou daqui a
  1 h, `ESPERA_SEM_CONTAS`) sem incrementar `tentativas`: falta de conta não é falha do job.
- **Coleta esgotada:** quando um `coletar_perfil` esgotava as tentativas, o worker empurrava
  `proxima_coleta_em` do perfil um intervalo à frente, para o agendador (que reativa jobs em
  `erro`) não repetir a falha a cada 5 minutos.
- Nenhuma dessas exceções atualizava as datas de coleta do perfil.

## Formatos de nó do instaloader (4.15.4)

O parser (`parse_post`) usava só a API pública de `instaloader.Post`, que cobre dois
formatos de nó:

- **Anônimo (GraphQL):** `Post(context, node)` com `__typename` (`GraphImage`,
  `GraphVideo`, `GraphSidecar`), `shortcode`, `taken_at_timestamp`,
  `edge_media_to_caption`, `edge_sidecar_to_children`, `display_url`, `is_video`. Fixado =
  `pinned_for_users` não vazio (`Post.is_pinned`).
- **Logado (API iPhone):** com sessão, `Profile.get_posts()` produz posts via
  `Post.from_iphone_struct`, a partir do dict de mídia com `code`, `taken_at`, `media_type`,
  `caption.text`, `image_versions2`, `carousel_media`, `video_versions`. Fixado =
  `iphone_struct.timeline_pinned_user_ids` não vazio.

Regras do parser: carrossel → `display_url` de cada filho (vídeo contribui com a capa);
imagem ou vídeo → `post.url` (a capa, no vídeo); `KeyError` ao ler as URLs → lista vazia;
legenda ausente → `""`; data por `date_local.astimezone(UTC)` (o `date_utc` do instaloader
usa `utcfromtimestamp`, depreciado e sem fuso). As fixtures sintéticas desses dois formatos
estavam em `backend/tests/fixtures/ig/`.

## Motivo da remoção

A conta de coleta passou a receber `feedback_required` do Instagram em toda consulta de
posts, embora funcionasse normalmente no app. Manter um pool de contas, sessões e
contornos de bloqueio ficou inviável para o projeto. A coleta passou a usar o actor
`apify/instagram-post-scraper` da Apify, que dispensa contas e proxies e cobra por post
retornado. Perfis marcados `inexistente` durante o bloqueio (como `ebetcel12` e `fica.bar`)
podiam ser falsos positivos; a migração `0004` devolve a `ativo` os que nunca foram
coletados, para a primeira coleta pela Apify reavaliá-los.
