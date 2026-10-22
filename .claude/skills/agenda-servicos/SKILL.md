---
name: agenda-servicos
description: Liga, desliga, reinicia e diagnostica os serviços da agenda cultural (Postgres, S3, API, front, workers de coleta e reconciliação) no macOS via launchd. Use quando pedirem para subir/parar/reiniciar a aplicação, ver se está rodando, ligar a coleta ou investigar por que nada é coletado.
---

# Serviços da agenda cultural

A aplicação roda do checkout principal (`/Users/ebetcel/orca/projects/mestrado-app`, branch `master`).
Os processos são agentes `launchd` (`~/Library/LaunchAgents/com.agenda.*.plist`), que sobem no login
e reiniciam sozinhos. Os contêineres usam `restart: unless-stopped` (precisa do Docker Desktop aberto).

| Serviço | Label launchd | Endereço / função | Log (`~/Library/Logs/agenda/`) |
|---|---|---|---|
| Front (Next, build de produção) | `com.agenda.web` | http://localhost:3000 | `web.log` |
| API (FastAPI) | `com.agenda.api` | http://localhost:8010/api/docs | `api.log` |
| Worker de coleta + extração | `com.agenda.worker` | agenda os lotes de coleta (Apify) a cada 5 min | `worker.log` |
| Worker de reconciliação | `com.agenda.worker-reconc` | **exatamente um** processo | `worker-reconc.log` |
| Postgres / SeaweedFS (S3) | contêineres do `docker-compose.yml` | `localhost:5432` / `localhost:8333` | `docker compose logs` |
| Mailpit (e-mails de login) | contêiner | http://localhost:8025 | |

## Ver o estado

```sh
launchctl list | grep com.agenda          # PID na 1ª coluna = rodando; "-" = parado
docker compose -f /Users/ebetcel/orca/projects/mestrado-app/docker-compose.yml ps
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8010/api/docs
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/entrar
tail -20 ~/Library/Logs/agenda/worker.log
```

## Ligar tudo (ordem importa)

```sh
cd /Users/ebetcel/orca/projects/mestrado-app
docker compose up -d postgres seaweedfs      # mailpit só se a porta 1025 estiver livre
cd backend && uv run alembic upgrade head    # se houve migração nova
U=$(id -u)
for s in api web worker-reconc worker; do
  launchctl bootstrap gui/$U ~/Library/LaunchAgents/com.agenda.$s.plist
done
```

**Antes de ligar `worker`, confirme que `APIFY_TOKEN` está em `backend/.env` e que a conta da Apify
tem saldo e limite de gasto configurado** (o limite de gasto da conta é a trava de custo). Se o
`worker.log` mostrar `ApifyRecusou` (401/402/403), o token é inválido ou o limite/saldo acabou: não
insista. Pare o worker, corrija o token ou o limite no console da Apify e só então religue. O worker
cria dois lotes por dia (`HORARIOS_COLETA`, padrão 08:00 e 18:00) e um lote imediato para @s novos.

## Parar / reiniciar

```sh
U=$(id -u)
launchctl bootout gui/$U/com.agenda.worker           # parar um serviço (troque o sufixo)
launchctl kickstart -k gui/$U/com.agenda.api         # reiniciar um serviço
```

Depois de mudar código: reinicie `api`, `worker` e `worker-reconc` com `kickstart -k`. Para o front,
rode `npm run build` em `web/` antes (os rewrites para a API são fixados no build) e então
`kickstart -k gui/$U/com.agenda.web`. Nunca deixe dois `worker-reconc` ao mesmo tempo.

## Diagnóstico rápido

```sh
cd /Users/ebetcel/orca/projects/mestrado-app
docker compose exec -T postgres psql -U agenda -d agenda -c \
  "select tipo, status, tentativas, executar_em, left(coalesce(erro_msg,''),80) from jobs where status<>'concluido' order by executar_em;" \
  -c "select username, status, ultima_coleta_em from perfis;"
cd backend && uv run agenda lotes          # últimos lotes (status, posts, custo) e o total estimado do mês
```

- **Nada é coletado e não há worker:** `launchctl list | grep worker` não mostra PID. Ligue (acima).
- **`@` fica "coletando…":** o `worker` ou o `worker-reconc` está parado, ou o lote de coleta falhou (veja `agenda lotes` e o `worker.log`).
- **Lote em `erro`:** `cd backend && uv run agenda coletar --perfil <username>` cria um lote novo agora (use `agenda coletar` para todos os acompanhados); para um post,
  `uv run agenda post-reprocessar <shortcode>`.
- **Porta 5432/1025 ocupada:** outro contêiner (de outro projeto ou worktree) a usa; pare-o ou mude a porta.
- **Link de login não chega:** abra http://localhost:8025 (Mailpit). Fora do computador local é preciso SMTP real e `APP_URL`.

## Se os plists sumirem

Cada plist é um agente com `RunAtLoad` + `KeepAlive`, `ThrottleInterval` 30, `WorkingDirectory` e `PATH`
(inclua `/opt/homebrew/bin` e o bin do node em `~/.nvm/versions/node/*/bin`), com estes `ProgramArguments`:

- `com.agenda.api`: `/opt/homebrew/bin/uv run agenda api --porta 8010` (cwd `backend/`)
- `com.agenda.worker`: `/opt/homebrew/bin/uv run agenda worker` (cwd `backend/`)
- `com.agenda.worker-reconc`: `/opt/homebrew/bin/uv run agenda worker-reconciliacao` (cwd `backend/`)
- `com.agenda.web`: `<node> node_modules/next/dist/bin/next start -p 3000` (cwd `web/`)

Saída padrão e de erro em `~/Library/Logs/agenda/<nome>.log`.
