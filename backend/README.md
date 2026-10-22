# Agenda cultural — backend (núcleo de dados e api)

Coleta posts de perfis do Instagram pela API da Apify (em lotes), extrai eventos com a OpenAI e os
reconcilia numa base única de eventos. O Postgres é a fonte da verdade e também a
fila de jobs: `coletar_lote` → `extrair_post` → `reconciliar_post`. A api (FastAPI)
serve o produto web do piloto: convites, login por link mágico, grupos e agenda.

## Pré-requisitos

- [uv](https://docs.astral.sh/uv/) (instala o Python 3.12 e as dependências).
- Docker com Compose (Postgres 16, SeaweedFS como S3 local e Mailpit como SMTP de
  desenvolvimento; os testes também usam Docker via testcontainers).
- Uma chave da OpenAI e um token da [Apify](https://apify.com) (a coleta usa o actor
  `apify/instagram-post-scraper`; não é preciso conta do Instagram).

## Primeira configuração

Todos os comandos abaixo rodam a partir de `backend/` (é onde o `.env` é lido).

```sh
cd backend
uv sync

# 1. Serviços locais (o docker-compose.yml fica na raiz do repositório)
docker compose -f ../docker-compose.yml up -d

# 2. Configuração
cp .env.example .env
# preencha OPENAI_API_KEY e APIFY_TOKEN (só no seu .env, nunca no .env.example);
# OPENAI_MODELO_EXTRACAO / OPENAI_MODELO_RECONCILIACAO já vêm preenchidos no exemplo

# 3. Banco (só precisa de DATABASE_URL)
uv run alembic upgrade head
```

O bucket do S3 é criado automaticamente no primeiro upload.

## Coleta (Apify) e perfis

Variáveis (veja `.env.example`): `APIFY_TOKEN` (obrigatória para coletar),
`HORARIOS_COLETA` (padrão `08:00,18:00`, fuso America/Sao_Paulo) e
`APIFY_PRECO_POR_POST` (padrão `0.0017`, usado só na estimativa de custo). **O limite de
gasto mensal da conta da Apify é a trava de custo**: configure-o no console da Apify.

Perfis a acompanhar (username sem `@`, minúsculo):

```sh
uv run agenda perfil-adicionar casadeshows
uv run agenda perfil-listar
uv run agenda coletar                     # cria já um lote de coleta (todos os acompanhados ou --perfil X)
uv run agenda lotes                       # últimos lotes (--ultimos N) e o custo estimado do mês
```

Perfis cadastrados pela CLI são "fixos": coletados sempre. Os demais (adicionados a
grupos pela api) só são coletados enquanto estiverem em algum grupo.

## Api (produto web)

```sh
uv run agenda api --porta 8010        # rotas em /api; documentação em /api/docs
uv run agenda convite-criar --usos 5 --dias 14   # mostra o código só agora
uv run agenda convite-listar
```

- Quem já tem conta pede o link em `POST /api/auth/entrar`; e-mail novo precisa de um
  código de convite e do nome. O link vale 15 minutos e uma vez; a sessão, 30 dias
  (cookie `sessao`).
- Em desenvolvimento, os e-mails vão para o Mailpit: <http://localhost:8025>. Os serviços
  do `docker compose` sobem a partir da raiz do repositório.
- Variáveis (ver `.env.example`): `APP_URL` (origem do front, usada no link do e-mail),
  `SMTP_*`, `EMAIL_REMETENTE`, `COOKIE_SEGURO` (`true` em produção, com HTTPS),
  `LIMITE_GRUPOS_POR_USUARIO` (10) e `LIMITE_PERFIS_POR_USUARIO` (30 @s distintos somando
  os grupos de quem os criou). A api não precisa das variáveis da OpenAI.
- O front (Next.js) repassa `/api/*` para a api: no navegador, tudo fica na origem do
  front, e o cookie de sessão também.

## Workers

Rode, cada um sob um supervisor que o reinicie se cair (systemd, supervisord,
`restart: unless-stopped` num container etc.) — um erro de banco, por exemplo,
derruba o processo em vez de ser engolido:

```sh
uv run agenda worker                      # coleta + extração; pode haver vários
uv run agenda worker-reconciliacao        # reconciliação: exatamente UM processo
```

O `worker` agenda sozinho dois lotes de coleta por dia (nos `HORARIOS_COLETA`) e um lote
imediato para cada @ novo (nunca coletado), e devolve à fila jobs travados. `--uma-vez`
processa o que estiver pronto e sai; `--tipos coletar_lote` limita a coleta. Se a Apify
recusar (401/402/403: token inválido, saldo ou limite de gasto), o lote vai para `erro`
sem retentativa e o log mostra ERROR; falhas de execução da Apify são retentadas.

## Consultar e corrigir

```sh
uv run agenda eventos --cidade "São Paulo" --de 2026-10-01 --ate 2026-10-31
uv run agenda post-reprocessar <shortcode>                         # refaz extração + reconciliação
uv run agenda post-reprocessar <shortcode> --etapa reconciliacao   # reaproveita a extração
uv run agenda deduplicar                    # lista duplicatas (mesmo dia, nome parecido); --aplicar funde
```

O worker de reconciliação já funde as duplicatas do dia de cada evento que um post toca.

## Avaliação (golden set)

```sh
uv run agenda avaliar --etapa extracao --golden golden/casos
uv run agenda avaliar --etapa reconciliacao --golden golden/casos
```

Chama a OpenAI de verdade e mostra o custo. Formato dos casos e cálculo das notas:
[golden/README.md](golden/README.md).

## Testes

```sh
uv run pytest -W error -q
```

Precisa do Docker rodando (sobe um Postgres descartável); não acessa a Apify nem
a OpenAI.
