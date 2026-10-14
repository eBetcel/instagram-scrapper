# Agenda cultural — backend (núcleo de dados e api)

Coleta posts de perfis do Instagram (instaloader), extrai eventos com a OpenAI e os
reconcilia numa base única de eventos. O Postgres é a fonte da verdade e também a
fila de jobs: `coletar_perfil` → `extrair_post` → `reconciliar_post`. A api (FastAPI)
serve o produto web do piloto: convites, login por link mágico, grupos e agenda.

## Pré-requisitos

- [uv](https://docs.astral.sh/uv/) (instala o Python 3.12 e as dependências).
- Docker com Compose (Postgres 16, SeaweedFS como S3 local e Mailpit como SMTP de
  desenvolvimento; os testes também usam Docker via testcontainers).
- Uma chave da OpenAI e pelo menos uma conta **dedicada** do Instagram para a coleta
  (nunca use a sua conta pessoal).

## Primeira configuração

Todos os comandos abaixo rodam a partir de `backend/` (é onde o `.env` é lido).

```sh
cd backend
uv sync

# 1. Serviços locais (o docker-compose.yml fica na raiz do repositório)
docker compose -f ../docker-compose.yml up -d

# 2. Configuração
cp .env.example .env
# gere a chave que cifra as sessões do Instagram e cole em CHAVE_SESSAO=
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# preencha também OPENAI_API_KEY; OPENAI_MODELO_EXTRACAO / OPENAI_MODELO_RECONCILIACAO
# já vêm preenchidos no exemplo

# 3. Banco (só precisa de DATABASE_URL)
uv run alembic upgrade head
```

O bucket do S3 é criado automaticamente no primeiro upload.

## Contas de coleta e perfis

Gere o arquivo de sessão do instaloader com a conta dedicada (pede a senha e, se
houver, o código de dois fatores) e cadastre-o; a sessão é guardada cifrada com
`CHAVE_SESSAO`:

```sh
uv run instaloader --login minha_conta_coleta   # grava a sessão em ~/.config/instaloader/session-minha_conta_coleta
uv run agenda conta-adicionar minha_conta_coleta --sessao-arquivo ~/.config/instaloader/session-minha_conta_coleta
```

(Em Linux e macOS o arquivo fica em `$XDG_CONFIG_HOME/instaloader/` ou, sem essa
variável, em `~/.config/instaloader/`.) Rodar `conta-adicionar` de novo
atualiza a sessão e reativa uma conta bloqueada.

Perfis a acompanhar (username sem `@`, minúsculo):

```sh
uv run agenda perfil-adicionar casadeshows
uv run agenda perfil-listar
uv run agenda coletar                     # força a coleta agora (todos ou --perfil X)
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

O `worker` agenda sozinho as coletas devidas (a cada `INTERVALO_COLETA_HORAS`) e
devolve à fila jobs travados. `--uma-vez` processa o que estiver pronto e sai.
Quando nenhuma conta de coleta está disponível, o job de coleta é adiado até a
primeira conta voltar, sem gastar tentativa; bloqueios aparecem no log como ERROR.

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

Precisa do Docker rodando (sobe um Postgres descartável); não acessa Instagram nem
OpenAI.
