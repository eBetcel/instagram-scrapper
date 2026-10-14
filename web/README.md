# Agenda — front web (Next.js)

Páginas do piloto: `/entrar`, `/` (agenda), `/evento/[id]`, `/grupos`, `/g/[slug]`
(pública) e `/conta`. O navegador só fala com esta origem: `/api/*` é repassado para a
api (`next.config.ts`), e o cookie de sessão fica aqui também.

## Rodar

Com o Postgres, o SeaweedFS e o Mailpit do `docker-compose.yml` da raiz no ar e a api
rodando (`cd ../backend && uv run agenda api --porta 8010`):

```sh
npm install
cp .env.example .env.local   # API_URL_INTERNA=http://localhost:8010
npm run dev                  # http://localhost:3000
```

O link de login chega no Mailpit (<http://localhost:8025>). `APP_URL` da api deve ser a
origem deste front (padrão `http://localhost:3000`).

> Os rewrites para a api são fixados no build: um `next build` usa o `API_URL_INTERNA`
> do momento do build.

## Testes

```sh
npm test        # Vitest (datas, formatação, clientes da api), com TZ=UTC
npm run lint
npm run e2e     # Playwright: recria o banco agenda_e2e, sobe api (8111) e front (3101)
```

O smoke (`e2e/piloto.spec.ts`) percorre o piloto inteiro: convite e login pelo Mailpit,
criar grupo, adicionar @s, agenda, evento, página pública vista sem login, outra pessoa
seguindo o grupo e saindo.

Next.js 16 com `cacheComponents`: toda leitura de cookie ou de `searchParams` fica dentro
de um `<Suspense>` na própria página (nenhum layout lê a sessão).
