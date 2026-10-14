# Fatia 2 — Produto web (piloto) — Design

Complementa `2026-10-09-agenda-cultural-instagram-design.md` (seções 1, 2, 4, 5, 7 e 9) e
`2026-10-14-deduplicacao-eventos-design.md`. Onde divergirem, vale esta.

## 1. Objetivo e contexto

Pôr o produto nas mãos de um **piloto com pessoas reais**, que entram por **código de
convite**: cada uma faz login por link mágico, monta grupos de @s, segue grupos de outras
pessoas pelo link e vê a agenda dos seus grupos no celular.

Sucesso:
1. Com um código de convite, uma pessoa cria a conta e entra pelo link do e-mail, sem
   senha.
2. Cria um grupo, adiciona @s (que aparecem como "coletando…" até a primeira coleta) e
   vê a agenda com os eventos desses perfis.
3. Compartilha `/g/<slug>`; outra pessoa, logada, segue o grupo e passa a ver os mesmos
   eventos na agenda dela; mudanças do dono aparecem para quem segue.
4. Cada pessoa tem no máximo 30 @s distintos somando os grupos dela; o custo de coleta e
   de IA fica limitado.
5. Testes de integração da API e smoke tests do front passando.

Fora do escopo: Telegram (Fatia 3; `/conta` só mostra o e-mail e "sair"), vitrine de
descoberta, hospedagem de produção, login por outros provedores.

## 2. Arquitetura

- **api** (FastAPI) no pacote `agenda` (`agenda/api/`), rodada por `agenda api` (uvicorn).
  Todas as rotas sob `/api`. Usa uma configuração própria (`ConfigApi`), sem exigir as
  variáveis da OpenAI.
- **web** (Next.js, App Router, TypeScript, Tailwind) em `web/` na raiz do repositório.
  O Next repassa `/api/:path*` para a api (`rewrites` para `API_URL_INTERNA`): o navegador
  só fala com a origem do Next, então o cookie de sessão é da mesma origem e não há CORS.
  Páginas são renderizadas no servidor do Next, que chama a api repassando o cookie;
  mutações vêm do navegador para `/api`.
- **worker** inalterado, exceto o agendador (seção 6).
- **Mailpit** no `docker-compose.yml` (SMTP em 1025, interface em 8025) para ver os
  e-mails em desenvolvimento.

## 3. Modelo de dados (migração `0003`)

- **`usuarios`**: id, email (único, minúsculo), nome (1–60 caracteres), criado_em.
- **`convites`**: id, codigo_hash (único), usos_restantes (int ≥ 0), expira_em (null =
  não expira), criado_em.
- **`tokens_login`**: id, usuario_id, token_hash (único), expira_em, usado_em, criado_em.
- **`sessoes`**: id, usuario_id, token_hash (único), expira_em, criado_em.
- **`grupos`**: id, dono_id, nome, descricao, slug (único), criado_em.
- **`grupo_perfis`**: grupo_id, perfil_id (PK composta), adicionado_em; apagar o grupo
  apaga as linhas.
- **`grupo_seguidores`**: grupo_id, usuario_id (PK composta), seguido_em; idem.
- **`perfis.fixo`** (bool, default false): perfis cadastrados pela CLI
  (`perfil-adicionar` passa a gravar `fixo = true`; a migração marca os perfis já
  existentes como fixos).

Tokens, sessões e convites guardam só o SHA-256 do valor; o valor sai uma única vez (no
e-mail, no cookie, na saída da CLI).

## 4. Autenticação e convites

### 4.1 Convites (CLI)

- `agenda convite-criar [--usos N=1] [--dias D]` imprime o código: 8 caracteres de
  `ABCDEFGHJKMNPQRSTUVWXYZ23456789`, mostrado como `XXXX-XXXX` (hífen e caixa ignorados
  na entrada).
- `agenda convite-listar`: prefixo do hash, usos restantes, validade.

### 4.2 Entrada

`POST /api/auth/entrar {email, convite?, nome?}`:
- e-mail inválido → 422;
- e-mail de usuário existente → envia o link → 202;
- e-mail novo sem `convite` → 409 `{"detail": "...", "precisa_convite": true}`;
- e-mail novo com convite inexistente, esgotado ou vencido → 422 "Código de convite
  inválido";
- e-mail novo com convite válido e sem `nome` → 422 "Informe seu nome";
- e-mail novo com convite válido e `nome` → cria o usuário, decrementa `usos_restantes` (na mesma
  transação, com um `UPDATE ... WHERE usos_restantes > 0` atômico), envia o link → 202;
- limite: no máximo 1 link por minuto e 5 por hora por e-mail (contando `tokens_login`);
  acima disso → 429 "Aguarde para pedir outro link".

O link é `{APP_URL}/api/auth/verificar?token=<token>`; o token vale 15 minutos e uma vez.

### 4.3 Verificação e sessão

`GET /api/auth/verificar?token=`: token válido → marca `usado_em`, cria a sessão
(30 dias), grava o cookie `sessao` (`HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` se
`COOKIE_SEGURO=true`) e redireciona (303) para `/`. Token inválido, usado ou vencido →
redireciona para `/entrar?erro=link`.

`POST /api/auth/sair` apaga a sessão e o cookie (204). `GET /api/eu` → `{id, email, nome}`
ou 401.

### 4.4 E-mail

Interface `EnviadorEmail.enviar(para, assunto, texto)`; `SmtpEnviador` (smtplib) e
`FakeEnviador` (guarda em memória) para testes. Assunto "Seu link de acesso à Agenda";
texto com o link e o aviso de validade de 15 minutos.

## 5. Grupos e perfis

- **Slug**: do nome (minúsculo, sem acento, hífens), sufixo `-2`, `-3`… se já existir.
  Não muda ao renomear.
- **Limites** (configuráveis): `LIMITE_GRUPOS_POR_USUARIO = 10`;
  `LIMITE_PERFIS_POR_USUARIO = 30`, contando @s distintos somados nos grupos que a pessoa
  é dona. Acima → 422 com mensagem.
- **Adicionar @** (`POST /api/grupos/{slug}/perfis {username}`, só o dono): normaliza
  (sem `@`, minúsculo, mesma regra da CLI; inválido → 422); cria o perfil se não
  existir; liga ao grupo (repetido → 200, sem duplicar); se o perfil nunca foi coletado,
  enfileira `coletar_perfil` imediata (`reativar_ou_enfileirar`, chave
  `coletar:<perfil_id>`).
- **Status exibido do @**: `privado` / `inexistente` (status do perfil); `coletando` se
  `ultima_coleta_em` é null; senão `ativo`.
- Só o dono edita, apaga e mexe nos @s (outro usuário → 403). O dono não "segue" o
  próprio grupo (seguir o próprio → 422).

## 6. Agendador

`agendar_coletas` passa a considerar só perfis `ativo` que estejam em pelo menos um
grupo **ou** sejam `fixo`. Um @ removido de todos os grupos deixa de ser coletado; os
eventos já extraídos continuam no banco.

## 7. Contrato da API

Erros: `{"detail": "<mensagem em português>"}`; 401 sem sessão, 403 sem permissão, 404,
409, 422, 429. Datas em ISO 8601 com fuso.

**Evento (resumo)**: `{id, titulo, inicio, hora_definida, fim, local_nome, cidade,
categoria, preco_texto, gratuito, preco_min, preco_max, link_ingresso, status, festival,
artistas, alterado, imagem}` — `alterado` = existe `evento_fontes` com `decisao =
'atualizacao'` criada nos últimos 7 dias; `imagem` = URL da primeira imagem do post de
origem mais antigo (`/api/posts/<shortcode>/imagens/0`) ou null.

| Rota | Auth | Resposta |
|---|---|---|
| `POST /api/auth/entrar` | — | seção 4.2 |
| `GET /api/auth/verificar` | — | seção 4.3 |
| `POST /api/auth/sair` | sim | 204 |
| `GET /api/eu` | sim | `{id, email, nome}` |
| `GET /api/agenda?de=&ate=&grupo=&categoria=&gratuito=` | sim | `{eventos: [Evento]}` |
| `GET /api/eventos/{id}` | — | Evento + `descricao`, `endereco`, `fontes: [{username, shortcode, url_instagram, publicado_em, decisao}]`, `revisoes: [{campo, valor_anterior, valor_novo, motivo, criado_em}]` |
| `GET /api/grupos` | sim | `{meus: [Grupo], seguidos: [Grupo]}` |
| `POST /api/grupos {nome, descricao?}` | sim | 201 Grupo |
| `GET /api/grupos/{slug}` | — | Grupo + `perfis: [{username, status}]`, `eventos: [Evento]` (próximos 30 dias), `sou_dono`, `sigo` (falsos sem sessão) |
| `PATCH /api/grupos/{slug} {nome?, descricao?}` | dono | Grupo |
| `DELETE /api/grupos/{slug}` | dono | 204 |
| `POST /api/grupos/{slug}/perfis {username}` | dono | 201/200 `{username, status}` |
| `DELETE /api/grupos/{slug}/perfis/{username}` | dono | 204 |
| `POST /api/grupos/{slug}/seguir` / `DELETE` | sim | 204 |
| `GET /api/posts/{shortcode}/imagens/{n}` | — | JPEG do storage, `Cache-Control: public, max-age=86400`; 404 se não houver |

**Grupo**: `{slug, nome, descricao, curador (nome do dono; o e-mail nunca é exposto),
n_perfis, n_seguidores}`.

**Agenda**: eventos com `inicio` em `[de 00:00, ate 23:59]` (São Paulo; padrão: hoje até
+7 dias) e ao menos uma `evento_fontes` cujo post é de um perfil em algum grupo que a
pessoa é dona ou segue; filtro `grupo` (slug) restringe a esse grupo; `categoria`;
`gratuito=true` → `gratuito` verdadeiro ou `preco_max = 0`. Ordem por `inicio`, máximo
500.

## 8. Front (`web/`)

Mobile-first, pt-BR, datas em São Paulo.

- `/entrar`: campo de e-mail; se a api responder `precisa_convite`, mostra os campos de
  código de convite e nome; depois de 202, "Enviamos um link para <email>". `?erro=link` mostra "Link
  inválido ou vencido".
- `/` (logado): filtros de período (hoje, fim de semana, semana, mês), grupo, categoria e
  "só gratuitos"; eventos agrupados por dia; card com miniatura, título, hora (ou
  "horário a confirmar"), local, cidade, preço, link do ingresso e selos (⚠️ alterado,
  ❌ cancelado, 🔴 esgotado, ⏸ adiado). Sem grupos: convite para criar um.
- `/evento/[id]` (público): detalhes, artistas, fontes com link para o Instagram e
  histórico de revisões.
- `/grupos` (logado): meus grupos e seguidos; criar grupo.
- `/g/[slug]` (público): nome, curador, @s e próximos eventos; botão Seguir/Deixar de
  seguir (sem sessão, leva a `/entrar`); metadados Open Graph com nome e descrição. Para
  o dono, a mesma página edita nome/descrição, adiciona e remove @s (com o status de
  cada um), copia o link e apaga o grupo.
- `/conta` (logado): nome, e-mail e "Sair".
- Sem sessão nas páginas logadas → redireciona para `/entrar`.

## 9. Configuração

`ConfigApi` (env): `DATABASE_URL`, `APP_URL` (ex. `http://localhost:3000`), `SMTP_HOST`
(`localhost`), `SMTP_PORTA` (1025), `SMTP_USUARIO`, `SMTP_SENHA`, `SMTP_TLS` (false),
`EMAIL_REMETENTE`, `COOKIE_SEGURO` (false), `LIMITE_GRUPOS_POR_USUARIO` (10),
`LIMITE_PERFIS_POR_USUARIO` (30), mais as variáveis de S3 já existentes (imagens). Web:
`API_URL_INTERNA` (ex. `http://localhost:8000`).

## 10. Testes

- **api** (pytest + testcontainers, padrão atual, `FakeEnviador`, `TestClient`): fluxo
  de convite (válido, esgotado, vencido, usos concorrentes), link (usado, vencido),
  limite de envio, sessão e sair; permissões (dono × outro × anônimo); limites de grupos
  e @s; adicionar @ enfileira coleta só se nunca coletado; status do @; agenda (dono,
  seguidor, filtros, evento de perfil fora dos grupos não aparece, `alterado`); slug
  único; imagens (200 e 404); agendador ignora perfil sem grupo e não fixo.
- **web**: smoke com Playwright contra a stack local (api + Postgres + Mailpit + Next):
  convite → link pelo Mailpit → criar grupo → adicionar @ ("coletando…") → agenda com
  evento semeado → página pública → outra conta segue o grupo e vê o evento.

## 11. Execução

Branch `fatia-2` (a partir de `start-project`). Dois planos, em sequência:
**2a — api** (seções 3–7, 9 e testes da api) e **2b — web** (seção 8 e Playwright).
