# Agenda Cultural via Instagram — Design

**Data:** 2026-10-09
**Status:** aguardando revisão

## 1. Objetivo e contexto

Um produto que lê perfis do Instagram por quem usa e entrega a agenda cultural (shows, festas, exposições, movimentações artísticas) já estruturada, num front-end web e numa newsletter semanal no Telegram.

**Usuário principal:** o público que frequenta eventos e quer saber "o que tem pra fazer" a partir das casas, artistas e coletivos que curte. O foco é descoberta e lazer, não ferramenta profissional.

**Conceito central, o grupo:** uma curadoria temática materializada como uma lista de @s (ex.: "Jazz em Natal", "Música em Natal"). Não existe "cidade" configurada no sistema: a cidade é uma propriedade de cada evento, extraída pela IA. Um mesmo @ pode estar em vários grupos.

**Critérios de sucesso:**
- Um post com flyer de evento vira um evento estruturado (título, data, hora, local, preço, link do ingresso, artistas, categoria) sem intervenção manual.
- O mesmo evento divulgado por perfis diferentes aparece uma única vez na agenda.
- Mudanças (adiamento, cancelamento, troca de preço ou horário, esgotado) atualizam o evento existente e ficam registradas no histórico.
- Um usuário cria um grupo, compartilha o link e outra pessoa passa a segui-lo.
- Toda segunda de manhã, quem vinculou o Telegram recebe a semana de eventos dos seus grupos.

## 2. Decisões tomadas

| Tema | Decisão |
|---|---|
| Natureza | Produto com usuários reais (multiusuário, com autenticação) |
| Escopo geográfico | Sem cidade fixa; a cidade vem do evento extraído |
| Compartilhamento | Seguir o grupo ao vivo, como uma playlist (mudanças do dono refletem para quem segue). Na v1, só por link, sem vitrine pública de descoberta. |
| Newsletter | Uma por usuário, com todos os eventos dos grupos que criou ou segue, cobrindo a semana seguinte. Envio fixo: segunda às 8h, para os eventos de segunda a domingo. |
| Stack | Backend Python com FastAPI; front-end Next.js; Postgres |
| Coleta | Scraper próprio, atrás da interface `Coletor` (troca de implementação sem impacto no pipeline) |
| IA | API da OpenAI: extração com visão e reconciliação com o banco |
| Autenticação | Link mágico por e-mail (sem senha) |
| Fuso horário | `America/Sao_Paulo` na v1 |

## 3. Arquitetura

### 3.1 Componentes

| Componente | Responsabilidade |
|---|---|
| **web** (Next.js) | Agenda, grupos, página pública do grupo, login, vínculo com o Telegram. Mobile-first. |
| **api** (FastAPI) | Autenticação, CRUD de grupos e perfis, consulta de eventos. |
| **worker** (Python, mesmo pacote da api) | Jobs agendados: coleta, extração, reconciliação, newsletter. Também roda o bot do Telegram. |
| **Postgres** | Fonte da verdade, e também fila de jobs via `SELECT ... FOR UPDATE SKIP LOCKED`, para não precisar de Redis. |
| **Armazenamento de objetos** (S3-compatível; SeaweedFS no ambiente local) | Cópia dos flyers. As URLs do CDN do Instagram expiram. |

A api e o worker compartilham o mesmo código (modelos, acesso ao banco, serviços) e rodam como processos separados.

### 3.2 Pipeline

```
Agendador ──► Coleta ──► posts (pendente)
                             │
                             ▼
                  Etapa A: Extração (OpenAI visão)
                             │  posts.extracao = [eventos extraídos]
                             ▼
                  Etapa B: Busca de candidatos (Postgres, sem IA)
                             │
                             ▼
                  Etapa C: Reconciliação (OpenAI texto)
                             │
                 ┌───────────┼──────────────┐
                 ▼           ▼              ▼
               NOVO      DUPLICADO     ATUALIZAÇÃO
           cria evento  vincula fonte  aplica mudanças + revisões
```

### 3.3 Coleta (scraper próprio)

**Interface:**
```python
class Coletor(Protocol):
    def posts_desde(self, username: str, desde: datetime | None) -> Iterable[PostColetado]: ...
```
`PostColetado` contém: shortcode, legenda, publicado_em, URLs das imagens (todas, no caso de carrossel).

**Comportamento:**
- O agendador seleciona os perfis com `status = ativo` que estão em pelo menos um grupo e cuja `proxima_coleta_em` já venceu. As coletas são espalhadas ao longo do dia, com intervalo aleatório entre perfis.
- A coleta é incremental: para ao encontrar um shortcode já salvo ou ao passar de `desde`.
- Perfil novo (que acabou de entrar no primeiro grupo) recebe prioridade na fila e uma carga inicial dos posts dos últimos 30 dias.
- As imagens são baixadas para o armazenamento de objetos no momento da coleta.

**Mitigações do scraper próprio:**
- Usa **contas dedicadas** num pool (`contas_coleta`), nunca a conta pessoal do operador. A sessão é persistida e criptografada.
- Limite de requisições por conta por hora, e backoff ao detectar bloqueio.
- Conta bloqueada recebe `bloqueada_ate` e o sistema passa para a próxima. Se todas estiverem bloqueadas, a coleta pausa e o admin é alertado.
- Perfil privado ou inexistente fica com o status correspondente e deixa de ser coletado. Isso é exibido na interface.

### 3.4 Etapa A — Extração

Uma chamada por post, à OpenAI com visão e **saída estruturada** (JSON Schema).

**Entrada:** imagens do post (redimensionadas para lado máximo de ~1024px), legenda, @ do autor e data de publicação. A data serve para resolver referências relativas como "sexta que vem".

**Saída:** `{ "eventos": [EventoExtraido] }`. A lista pode ser vazia (o post não é sobre evento) ou ter vários itens (um flyer de "agenda do mês").

**`EventoExtraido`:**

| Campo | Tipo | Observação |
|---|---|---|
| `titulo` | string | obrigatório para virar evento |
| `descricao` | string \| null | resumo curto |
| `data_inicio` | date | obrigatório para virar evento |
| `hora_inicio` | time \| null | |
| `data_fim`, `hora_fim` | date/time \| null | |
| `local_nome` | string \| null | |
| `endereco` | string \| null | |
| `cidade` | string \| null | |
| `categoria` | enum | `show`, `festa`, `exposicao`, `teatro`, `cinema`, `oficina`, `festival`, `outro` |
| `preco_texto` | string \| null | texto original, ex.: "R$30 antecipado / R$40 na porta" |
| `gratuito` | bool \| null | |
| `preco_min`, `preco_max` | decimal \| null | em BRL |
| `link_ingresso` | string \| null | URL, ou a pista textual ("link na bio", "Sympla") |
| `artistas` | string[] | |
| `status_indicado` | enum \| null | `adiado`, `cancelado`, `esgotado`, se o post disser |
| `confianca` | objeto | de 0 a 1 para `data_inicio`, `hora_inicio` e `local_nome` |

O resultado é salvo em `posts.extracao`. O modelo é configurável por variável de ambiente (`OPENAI_MODELO_EXTRACAO`).

**Regras pós-extração:** itens sem `titulo` ou sem `data_inicio` são descartados. Itens com data já passada também são descartados.

### 3.5 Etapa B — Busca de candidatos

Para cada evento extraído, o sistema busca no máximo 5 eventos futuros (ou recém-passados, até 7 dias) que satisfaçam **pelo menos um** dos critérios:
- similaridade de `titulo` acima do limiar (`pg_trgm`);
- interseção ou similaridade de `artistas`;
- mesmo `local_nome` (por similaridade) **e** mesma data.

A busca de propósito não exige a mesma data, porque um adiamento muda a data. Os candidatos são ordenados por um escore combinado.

### 3.6 Etapa C — Reconciliação

Uma chamada à OpenAI, só com texto e saída estruturada, com modelo configurável (`OPENAI_MODELO_RECONCILIACAO`) e mais barato que o da Etapa A.

**Entrada:** o evento extraído, a legenda original, o @ do autor, a data do post e os candidatos (com seus campos atuais).

**Saída:**
```json
{
  "decisao": "NOVO" | "DUPLICADO" | "ATUALIZACAO",
  "evento_id": "<id do candidato>" | null,
  "mudancas": [{ "campo": "...", "valor_novo": "..." }],
  "motivo": "texto curto"
}
```

**Efeitos (numa transação só):**
- `NOVO`: cria o `evento` e uma `evento_fontes` com decisão `novo`.
- `DUPLICADO`: cria uma `evento_fontes` com decisão `duplicado`. Campos nulos do evento podem ser preenchidos com dados do novo post (ex.: o link do ingresso que só a casa divulgou), cada um gerando uma revisão.
- `ATUALIZACAO`: aplica `mudancas` ao evento, cria um registro em `revisoes_evento` para cada campo alterado (antes, depois, post, motivo) e uma `evento_fontes` com decisão `atualizacao`.

Se `evento_id` não estiver entre os candidatos enviados, a resposta é tratada como inválida.

**Concorrência:** a Etapa C roda **em série**, com um único worker consumindo esse tipo de job, para evitar que dois posts do mesmo evento processados ao mesmo tempo criem duplicatas. A coleta e a Etapa A rodam em paralelo.

**Reprocessamento:** como `posts.extracao` fica salvo, é possível rodar de novo só a Etapa C, por exemplo depois de melhorar o prompt de reconciliação.

## 4. Modelo de dados

### Usuários e curadoria
- **`usuarios`**: id, email (único), nome, criado_em
- **`tokens_login`**: id, usuario_id, token_hash, expira_em, usado_em
- **`telegram_vinculos`**: usuario_id (PK), chat_id, ativo, vinculado_em
- **`telegram_tokens_vinculo`**: token_hash, usuario_id, expira_em
- **`grupos`**: id, dono_id, nome, descricao, slug (único), criado_em
- **`grupo_perfis`**: grupo_id, perfil_id (PK composta)
- **`grupo_seguidores`**: grupo_id, usuario_id, seguido_em (PK composta)

### Coleta
- **`perfis`**: id, username (único, minúsculo, sem @), status (`ativo` | `privado` | `inexistente`), ultima_coleta_em, proxima_coleta_em, criado_em
- **`contas_coleta`**: id, usuario_ig, sessao_criptografada, status (`ativa` | `bloqueada` | `desativada`), bloqueada_ate, ultimo_uso_em
- **`posts`**: id, perfil_id, shortcode (único), legenda, publicado_em, imagens (text[], chaves no storage), status (`pendente` | `extraido` | `reconciliado` | `erro`), extracao (jsonb), modelo_extracao, tokens_entrada, tokens_saida, custo_estimado, erro_msg, criado_em

### Eventos
- **`eventos`**: id, titulo, descricao, inicio (timestamptz), fim (timestamptz \| null), hora_definida (bool), local_nome, endereco, cidade, categoria, preco_texto, gratuito, preco_min, preco_max, link_ingresso, artistas (text[]), status (`ativo` | `adiado` | `cancelado` | `esgotado`), criado_em, atualizado_em
  - Índices `pg_trgm` em `titulo` e `local_nome`; índice em `inicio`.
  - `hora_definida = false` quando o post só informa a data. O front mostra "horário a confirmar".
- **`evento_fontes`**: evento_id, post_id, decisao (`novo` | `duplicado` | `atualizacao`), criado_em
- **`revisoes_evento`**: id, evento_id, post_id, campo, valor_anterior, valor_novo, motivo, criado_em

### Infraestrutura
- **`jobs`**: id, tipo (`coletar_perfil` | `extrair_post` | `reconciliar_post` | `enviar_newsletter` | ...), payload (jsonb), status (`pendente` | `executando` | `concluido` | `erro`), tentativas, max_tentativas, executar_em, erro_msg

### Agenda de um usuário
São os eventos com `inicio` no período que tenham **pelo menos uma** `evento_fontes` cujo post pertença a um perfil presente em algum grupo que o usuário criou ou segue. Um evento postado só por um perfil fora dos grupos do usuário não aparece para ele.

## 5. Front-end (Next.js)

| Rota | Conteúdo |
|---|---|
| `/` | Agenda agrupada por dia. Filtros: período (hoje, fim de semana, semana, mês), grupo, categoria, só gratuitos. Card: miniatura do flyer, título, hora (ou "horário a confirmar"), local, preço, link do ingresso, selo de status (⚠️ alterado nos últimos 7 dias, ❌ cancelado, 🔴 esgotado, ⏸ adiado). |
| `/evento/[id]` | Detalhes, posts de origem (com link para o Instagram) e histórico de revisões. |
| `/grupos` | Meus grupos e grupos seguidos. Criar e editar grupo, adicionar e remover @s. Um @ recém-adicionado aparece como "coletando…" até a primeira coleta; @s privados ou inexistentes ficam sinalizados. |
| `/g/[slug]` | Página pública do grupo (sem login): nome, curador, @s e próximos eventos. O botão "Seguir" exige login. Só o dono edita. |
| `/conta` | Vincular ou desvincular o Telegram. |
| `/entrar` | Formulário de e-mail para receber o link mágico. |

A autenticação é feita pela api: o link mágico expira em 15 minutos e só pode ser usado uma vez. A sessão fica em cookie `httpOnly`.

## 6. Telegram

- **Vínculo:** em `/conta`, "Conectar Telegram" gera um token de uso único (válido por 15 min) e abre `https://t.me/<bot>?start=<token>`. O bot recebe `/start <token>` e grava o `chat_id`.
- **Comandos:** `/start` (vincular) e `/parar` (desativa a newsletter, `ativo = false`).
- **Newsletter:** toda segunda às 8h (`America/Sao_Paulo`), um job por usuário com vínculo ativo.
  - Conteúdo: eventos de segunda a domingo da agenda do usuário, agrupados por dia, cada um com título, hora, local, preço e link do ingresso. Eventos alterados, cancelados, adiados ou esgotados aparecem sinalizados.
  - Mensagens acima de 4096 caracteres são divididas em várias, sempre em fronteira de evento. A última termina com um link para a agenda completa.
  - Usuário sem eventos na semana não recebe mensagem.
- **Alertas de admin:** o mesmo bot envia para o `chat_id` de admin (configurado por variável de ambiente) os avisos de: todas as contas de coleta bloqueadas, jobs que esgotaram as tentativas e taxa de erro da OpenAI acima do normal.

## 7. Tratamento de erros

| Situação | Comportamento |
|---|---|
| Falha em qualquer job | Retry com backoff exponencial até `max_tentativas`; depois `status = erro` e o job entra no alerta de admin |
| Conta de coleta bloqueada | Recebe `bloqueada_ate` e o sistema rotaciona para a próxima; sem contas disponíveis, a coleta pausa e o admin é alertado |
| Perfil privado ou inexistente | O perfil recebe o status correspondente, para de ser coletado e fica sinalizado na interface |
| OpenAI: timeout ou rate limit | Retry |
| OpenAI: resposta fora do schema, ou `evento_id` fora dos candidatos | Mais uma tentativa; depois o post fica com `status = erro` e pode ser reprocessado |
| Falha ao enviar no Telegram (ex.: usuário bloqueou o bot) | Erro 403 desativa o vínculo; outros erros têm retry |

## 8. Custos

- Só posts novos vão para a IA (deduplicação por `shortcode` antes da Etapa A).
- As imagens são redimensionadas antes da visão.
- A Etapa C usa um modelo mais barato e recebe só texto.
- Cada post registra tokens e custo estimado, o que permite medir o custo por perfil.
- Cada perfil é coletado uma única vez, independentemente de quantos grupos o incluam.

## 9. Testes

- **Unitários:** resolução de datas relativas, normalização de preço, regras pós-extração, montagem e divisão da newsletter, validação da saída da reconciliação.
- **Integração (pytest + testcontainers com Postgres real):** endpoints da api, busca de candidatos (Etapa B), efeitos transacionais da Etapa C, fila de jobs. A OpenAI usa respostas gravadas e o scraper usa um `Coletor` falso.
- **Parser do scraper:** testes contra respostas salvas do Instagram.
- **Golden set:** ~50 posts reais anotados à mão (imagens + JSON esperado + decisão de reconciliação esperada) e um script de avaliação que mede a acurácia por campo e das decisões. Roda manualmente quando o prompt ou o modelo mudar, fora do CI.
- **Front:** smoke tests com Playwright para login, criar grupo, ver agenda, abrir a página pública e seguir.

## 10. Fatiamento da implementação

Cada fatia tem o seu próprio plano de implementação.

1. **Fatia 1, núcleo de dados:** esqueleto do repositório, Docker Compose (Postgres, MinIO), esquema do banco, fila de jobs, `Coletor` com scraper próprio, Etapas A, B e C, e uma CLI de admin (adicionar perfil, rodar coleta, reprocessar post, listar eventos). Também entra o golden set e o script de avaliação. Ainda sem usuários nem grupos: os perfis são cadastrados pela CLI.
2. **Fatia 2, produto web:** autenticação por link mágico, grupos, seguidores, páginas do Next.js e página pública. O cadastro de perfis passa a vir dos grupos.
3. **Fatia 3, Telegram:** bot, vínculo, newsletter semanal e alertas de admin.

## 11. Fora de escopo (v1)

- Vitrine pública de descoberta de grupos
- Dia e horário da newsletter configuráveis pelo usuário
- Login com Google ou outros provedores
- Fusos horários diferentes de `America/Sao_Paulo`
- Leitura de Stories e Reels (só posts do feed, inclusive carrosséis)
- Escolha da hospedagem de produção
