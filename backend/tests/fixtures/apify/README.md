# Fixtures da Apify

Respostas cruas (lista de itens do dataset) do actor `apify/instagram-post-scraper`
(`nH2AHrwxeTRJoN5hX`), rota `run-sync-get-dataset-items`, gravadas em 22/10/2026.
Todas as execuções usaram `resultsLimit=3`, `skipPinnedPosts=true`, `dataDetailLevel="basicData"`
(HTTP 201 em todas). Custo total aproximado: 13 itens, cerca de US$ 0,02 (7 + 1 + 5 itens).

| Arquivo | Entrada | Itens | Cobre |
|---|---|---|---|
| `lote_misto.json` | `username=["festivalmada","jazznobardenazare","perfil-que-nao-existe-agenda-xyz"]`, `onlyPostsNewerThan="30 days"` | 7 (6 posts + 1 erro) | Image, Sidecar, Video, legenda preenchida, erro `not_found`, posts de coautoria |
| `janela_horas.json` | `username=["jazznobardenazare"]`, `onlyPostsNewerThan="12 hours"` | 1 (erro) | janela em horas; item `no_items` |
| `extra_privado_legenda_vazia.json` | `username=["banksy","private","joe"]` | 5 (3 posts + 2 erros) | legenda vazia (`""`), Video, Sidecar, erro `not_found` |

Não foi observado: legenda `null` (só `""`) nem perfil privado confirmado (nenhum perfil privado conhecido foi usado;
o erro `no_items` é descrito pela API como "vazio ou privado", sem distinguir os dois casos).

## (a) `onlyPostsNewerThan` aceita horas?

Sim, a API aceitou `"12 hours"` sem erro de validação (HTTP 201). A resposta foi um único item de erro `no_items`
(nenhum post). Janela vazia NÃO vem como lista vazia, vem como item com `error: "no_items"`.

Ressalva: a filtragem por horas NÃO está confirmada. Não havia post dentro das últimas 12 h, então não há controle
positivo; a checagem "só vieram posts das últimas 12 h" foi satisfeita vacuamente (zero posts). Só se sabe que o
valor é aceito sem erro de validação.

## (b) Que campo identifica a entrada de origem?

- Posts normais: **nenhum** campo de entrada. Não há `inputUrl` nem `username` nos posts; só `ownerUsername`
  (ex.: `"jazznobardenazare"`). O `ownerUsername` pode ser diferente do perfil pedido (posts de coautoria): pedindo
  `festivalmada`, vieram `cartolamag` e `toca_uol` como donos. Nos casos observados, o perfil pedido aparece em
  `coauthorProducers[].username` (itens 4 e 5 de `lote_misto.json`: `["festivalmada"]` e
  `["festivalmada","sussekind",...]`). Esse mapeamento foi apenas observado, não é garantido pela API.
- Itens de erro `not_found`: `username` (ex.: `"perfil-que-nao-existe-agenda-xyz"`) e `url`
  (ex.: `"https://www.instagram.com/perfil-que-nao-existe-agenda-xyz"`).
- Itens de erro `no_items`: `inputUrl` (ex.: `"https://www.instagram.com/jazznobardenazare"`) e `url`; não têm `username`.

Chaves dos posts (basicData): `caption, commentsCount, dimensionsHeight, dimensionsWidth, displayUrl, hashtags, id,
isPinned, likesCount, ownerFullName, ownerId, ownerUsername, shortCode, timestamp, type, url, videoUrl`
(+ `coauthorProducers` em parte). Não há `images` nos Sidecar com basicData.
Chaves de erro: `not_found` -> `error, errorDescription, url, username`;
`no_items` -> `error, errorDescription, inputUrl, requestErrorMessages, url`.

## Mensagens de erro vistas (textos exatos)

| `error` | `errorDescription` |
|---|---|
| `not_found` | `Profile does not exist` |
| `no_items` | `Empty or private data for provided input` |

## Filtro de janela em horas (R15)

Verificado em 22/10/2026 com `ApifyColetor.coletar(["natgeo"], janela="24 hours", limite=3)`:
3 posts devolvidos, nenhum erro, todos publicados dentro das últimas 24 h (17,2 h, 20,3 h e 23,3 h
antes da consulta). O filtro `onlyPostsNewerThan` em horas é aceito e respeitado. Como o limite (3)
foi atingido, isso não mostra se há mais posts na janela, só que nenhum item veio de fora dela.
