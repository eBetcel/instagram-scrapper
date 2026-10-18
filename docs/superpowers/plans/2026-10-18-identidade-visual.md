# Identidade visual e componentes do front — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aplicar ao front `web/` a identidade visual da spec (creme + terracota, Fraunces + Inter, modo escuro automático, navegação inferior no celular) por meio de tokens no Tailwind 4 e uma pequena biblioteca de componentes em `src/components/ui/`.

**Architecture:** Tokens são variáveis CSS em `:root` (redefinidas em `prefers-color-scheme: dark`) e expostas ao Tailwind com `@theme inline`, então os utilitários (`bg-fundo`, `text-tinta`…) trocam de tema sozinhos. As classes de cada variante saem de funções puras em `src/components/ui/estilos.ts` (testadas no Vitest, sem JSX); os componentes `.tsx` só montam markup em cima delas. As telas migram para esses componentes sem mudar textos, rótulos ou `role`.

**Tech Stack:** Next.js 16 (App Router, `cacheComponents`), React 19, Tailwind CSS 4, `next/font/google`, Vitest 3 (ambiente node), Playwright.

**Spec:** `docs/superpowers/specs/2026-10-18-identidade-visual-design.md`

## Global Constraints

- Pré-requisito: a árvore de trabalho começa limpa. Hoje há mudanças não commitadas da Fatia 2 em `web/src/app/page.tsx`, `web/src/app/g/[slug]/EditorGrupo.tsx`, `web/src/lib/tipos.ts`, `web/src/lib/pendentes*.ts`, `web/e2e/piloto.spec.ts`, `web/README.md` e `backend/`. Elas são da pessoa: **não commitar nem descartar**; pare e peça que ela as commite antes da Task 1.
- Next 16 difere do que você conhece: leia `web/node_modules/next/dist/docs/01-app/01-getting-started/13-fonts.md` antes de mexer em fontes, e o guia relevante em `node_modules/next/dist/docs/` antes de qualquer API do Next.
- Nenhuma dependência nova (nem runtime, nem teste, nem ícones).
- Nenhum texto visível, rótulo, `aria-label` ou `role` usado em `web/e2e/piloto.spec.ts` pode mudar; o e2e não é editado.
- Tokens de cor (claro / escuro): `fundo #faf8f3/#181715`, `superficie #fdfbf7/#211f1c`, `suave #f1ebe0/#2a2824`, `linha #e6dfd5/#35322d`, `tinta #1c1a17/#f5f1ea`, `texto #3d3a35/#d6d1c8`, `apagado #6c6860/#9e998f`, `acento #c8613f/#de7a58`, `acento-forte #a64c2e/#ec9070`, `erro #b93c3c/#e57373`, `sucesso #3f7a52/#7fbf8f`, mais `sobre-acento #ffffff/#181715` (texto do botão primário).
- Texto pequeno ou link em acento usa sempre `acento-forte`; `acento` puro só como fundo do botão primário e em bordas/anéis.
- Raios: 8px (`rounded-lg` do Tailwind 4 = 0.5rem) em botões, campos e flyer no card; 12px (`rounded-xl`) em cards e flyer no detalhe; `rounded-full` em selos e chips.
- Alturas mínimas: botão `md` e campos 44px (`min-h-11`), botão `sm` e chips 36px (`min-h-9`), itens da navegação inferior 56px.
- Foco: `focus-visible:` anel de 3px em `acento` a 25% (`ring-[3px] ring-acento/25`), campos com `border-acento`.
- Ao fim, nenhuma classe `stone-*`, `blue-*`, `amber-*`, `red-*` ou `emerald-*` em `web/src`.
- O layout raiz continua sem ler sessão, cookies ou `searchParams`.
- Commits em português no formato `feat(web): …` / `test(web): …`, terminando com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Item ativo da navegação em rotas filhas** — em `/evento/12` a pessoa espera "Agenda" ativo; em `/g/jazz` espera "Grupos" ativo; em `/entrar`, nenhum. (Teste em Task 4.)
2. **Card com dados faltando ou longos** — evento sem flyer, sem hora definida ("horário a confirmar"), sem preço, ou com título/local longo sem espaços não pode estourar a largura do card. (`min-w-0` + `break-words`; verificação visual com dado longo em Task 5.)
3. **Linha de categorias em tela de 320px** — os 10 chips rolam dentro da própria linha; a página nunca ganha rolagem horizontal. (Verificação em Task 5 e na Task 9.)
4. **Elementos fixos cobrindo conteúdo** — o rótulo de dia `sticky` fica logo abaixo do cabeçalho (`top-14`), e o último card/botão da página não fica escondido atrás da navegação inferior nem da barra do iPhone. (Verificação em Task 4 e Task 9.)
5. **Modo escuro em estados não-padrão** — botão primário desabilitado, aviso de erro, chip ativo e anel de foco continuam legíveis no escuro. (Capturas na Task 9.)

---

### Task 1: Tokens, fontes e base do `body`

**Files:**
- Modify: `web/src/app/globals.css`
- Modify: `web/src/app/layout.tsx` (só `<html>`/`<body>`; o cabeçalho muda na Task 4)

**Interfaces:**
- Produces: utilitários Tailwind `bg-/text-/border-/ring-` para `fundo`, `superficie`, `suave`, `linha`, `tinta`, `texto`, `apagado`, `acento`, `acento-forte`, `erro`, `sucesso`, `sobre-acento`; famílias `font-serifa` (Fraunces) e `font-sans` (Inter).

- [ ] **Step 1: Escrever os tokens em `globals.css`**

Variáveis cruas em `:root` (ex.: `--fundo: #faf8f3`) com os valores das Global Constraints, redefinidas em `@media (prefers-color-scheme: dark) { :root { … } }`, e `color-scheme: light dark` em `:root`. Exponha com `@theme inline { --color-fundo: var(--fundo); …; --font-serifa: var(--font-fraunces), Georgia, serif; --font-sans: var(--font-inter), system-ui, sans-serif; }`. `inline` é obrigatório: sem ele o utilitário congela o valor claro. Remova a regra antiga de `font-family` do `body`.

- [ ] **Step 2: Carregar as fontes em `layout.tsx`**

`Fraunces({ subsets: ["latin"], variable: "--font-fraunces", display: "swap" })` e `Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" })` de `next/font/google`; aplique as duas `.variable` no `<html>`. `body`: troque `bg-stone-50 text-stone-900` por `bg-fundo text-texto font-sans`.

- [ ] **Step 3: Verificar build e lint**

Run: `cd web && npm run lint && npx next build`
Expected: ambos sem erro; páginas ainda com classes `stone-*` antigas, o que é esperado nesta task.

- [ ] **Step 4: Commit**

```bash
git add web/src/app/globals.css web/src/app/layout.tsx
git commit -m "feat(web): tokens de cor, modo escuro e fontes Fraunces/Inter"
```

---

### Task 2: Estilos puros e componentes com variantes (`Botao`, `Chip`, `Selo`, `Aviso`)

**Files:**
- Create: `web/src/components/ui/estilos.ts`
- Test: `web/src/components/ui/estilos.test.ts`
- Create: `web/src/components/ui/Botao.tsx`, `Chip.tsx`, `Selo.tsx`, `Aviso.tsx`

**Interfaces:**
- Consumes: tokens da Task 1.
- Produces (em `estilos.ts`, sem JSX — o Vitest roda em ambiente node e não transforma `.tsx` com `jsx: preserve`):
  - `type VarianteBotao = "primario" | "secundario" | "fantasma" | "perigo"`; `type TamanhoBotao = "md" | "sm"`
  - `classesBotao(variante: VarianteBotao = "secundario", tamanho: TamanhoBotao = "md"): string`
  - `classesChip(ativo: boolean): string`
  - `type TomSelo = "neutro" | "acento"`; `classesSelo(tom: TomSelo = "neutro"): string`
  - `type TipoAviso = "erro" | "info" | "sucesso"`; `classesAviso(tipo: TipoAviso = "erro"): string`
  - `const foco: string` — as classes de foco das Global Constraints, reusadas pelos componentes.
- Produces (componentes):
  - `Botao(props: { variante?, tamanho?, className?, children } & ({ href: string; externo?: boolean } | ButtonHTMLAttributes<HTMLButtonElement>))` — com `href` e `externo` renderiza `<a target="_blank" rel="noopener noreferrer">`; com `href` sem `externo`, `next/link`; senão `<button>` com `type="button"` como padrão (o chamador passa `type="submit"`).
  - `Chip(props: { ativo: boolean; onClick: () => void; children })` — `<button type="button" aria-pressed={ativo}>`. (A spec cita `href`; nenhuma tela usa, então fica de fora.)
  - `Selo(props: { tom?: TomSelo; children })` — `<span>`.
  - `Aviso(props: { tipo?: TipoAviso; children })` — `<p>` com `role="alert"` para `erro` e `role="status"` para os demais.

- [ ] **Step 1: Escrever os testes que falham**

```ts
import { describe, expect, it } from "vitest";
import { classesAviso, classesBotao, classesChip, classesSelo } from "./estilos";

describe("classesBotao", () => {
  it("primario usa o acento como fundo e o texto sobre-acento", () => {
    const c = classesBotao("primario");
    expect(c).toContain("bg-acento");
    expect(c).toContain("text-sobre-acento");
    expect(c).toContain("active:bg-acento-forte");
  });
  it("md tem 44px e sm tem 36px", () => {
    expect(classesBotao("primario", "md")).toContain("min-h-11");
    expect(classesBotao("primario", "sm")).toContain("min-h-9");
  });
  it("padrão é secundario md, com borda linha", () => {
    const c = classesBotao();
    expect(c).toContain("border-linha");
    expect(c).toContain("bg-superficie");
    expect(c).toContain("min-h-11");
  });
  it("fantasma e perigo não têm fundo", () => {
    expect(classesBotao("fantasma")).toContain("text-acento-forte");
    expect(classesBotao("perigo")).toContain("text-erro");
    expect(classesBotao("perigo")).not.toContain("bg-acento");
  });
  it("todas as variantes desabilitam com opacidade", () => {
    for (const v of ["primario", "secundario", "fantasma", "perigo"] as const) {
      expect(classesBotao(v)).toContain("disabled:opacity-50");
    }
  });
});

describe("classesChip", () => {
  it("ativo inverte para tinta", () => {
    expect(classesChip(true)).toContain("bg-tinta");
    expect(classesChip(true)).toContain("text-fundo");
  });
  it("inativo tem borda linha e não usa tinta de fundo", () => {
    expect(classesChip(false)).toContain("border-linha");
    expect(classesChip(false)).not.toContain("bg-tinta");
  });
  it("tem 36px de altura", () => expect(classesChip(false)).toContain("min-h-9"));
});

describe("classesSelo", () => {
  it("neutro usa suave, acento usa acento-forte", () => {
    expect(classesSelo("neutro")).toContain("bg-suave");
    expect(classesSelo("acento")).toContain("text-acento-forte");
  });
});

describe("classesAviso", () => {
  it("erro usa a cor de erro; info e sucesso usam a de sucesso", () => {
    expect(classesAviso("erro")).toContain("text-erro");
    expect(classesAviso("info")).toContain("text-sucesso");
    expect(classesAviso("sucesso")).toContain("text-sucesso");
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run src/components/ui/estilos.test.ts`
Expected: FAIL — `Failed to resolve import "./estilos"`.

- [ ] **Step 3: Implementar `estilos.ts`**

Valores da spec §4: botão com `inline-flex items-center justify-center gap-1.5 rounded-lg font-medium` + tamanho (`md`: `min-h-11 px-4 text-sm`; `sm`: `min-h-9 px-3 text-sm`) + variante + `foco` + `disabled:opacity-50 disabled:cursor-default`. Chip: `min-h-9 px-3.5 rounded-full border text-sm font-medium whitespace-nowrap`. Selo: `rounded-full px-2.5 py-0.5 text-xs font-medium`; acento `bg-acento/12 text-acento-forte`. Aviso: `rounded-lg border px-3 py-2 text-sm` + `bg-<cor>/8 border-<cor>/25 text-<cor>`.

- [ ] **Step 4: Rodar e ver passar**

Run: `cd web && npx vitest run src/components/ui/estilos.test.ts`
Expected: PASS (10 testes).

- [ ] **Step 5: Criar `Botao.tsx`, `Chip.tsx`, `Selo.tsx`, `Aviso.tsx`** com as assinaturas de Interfaces. Nenhum leva `"use client"` (não usam hooks); funcionam em componentes de servidor e de cliente.

- [ ] **Step 6: Verificar**

Run: `cd web && npm test && npm run lint`
Expected: tudo PASS, lint sem erros.

- [ ] **Step 7: Commit**

```bash
git add web/src/components/ui
git commit -m "feat(web): componentes Botao, Chip, Selo e Aviso com estilos testados"
```

---

### Task 3: Componentes de formulário e contêineres

**Files:**
- Modify: `web/src/components/ui/estilos.ts`, `web/src/components/ui/estilos.test.ts`
- Create: `web/src/components/ui/Campo.tsx` (exporta `Campo` e `AreaTexto`), `Seletor.tsx`, `Cartao.tsx`, `Titulo.tsx`, `Vazio.tsx`, `Carregando.tsx`

**Interfaces:**
- Consumes: `foco` de `estilos.ts`.
- Produces:
  - `classesCampo(comErro: boolean): string` em `estilos.ts`.
  - `Campo(props: InputHTMLAttributes<HTMLInputElement> & { rotulo?: string; erro?: string })` e `AreaTexto(props: TextareaHTMLAttributes<HTMLTextAreaElement> & { rotulo?: string; erro?: string })` — com `rotulo`, `<label htmlFor={id}>` visível (13px/500, `text-texto`) e `id` vindo de `props.id ?? useId()`; com `erro`, `<p id={id+"-erro"} className="text-sm text-erro">` e `aria-describedby`/`aria-invalid`. São `"use client"` (usam `useId`).
  - `Seletor(props: SelectHTMLAttributes<HTMLSelectElement>)` — `<select>` com `appearance-none`, `classesCampo(false)`, `pr-9` e seta SVG absoluta (`pointer-events-none`, `text-apagado`).
  - `Cartao(props: { as?: "div" | "article" | "section" | "form" | "ul"; className?: string; children } & HTMLAttributes<HTMLElement>)` — `bg-superficie border border-linha rounded-xl shadow-[0_1px_3px_rgb(20_20_19/0.06)] dark:shadow-none`; repassa as demais props (o `form` precisa de `onSubmit`).
  - `Titulo(props: { nivel: 1 | 2; className?: string; children })` — `h1`: `font-serifa text-[30px] md:text-[32px] leading-tight tracking-[-0.02em] text-tinta`; `h2`: `font-serifa text-xl tracking-[-0.01em] text-tinta`.
  - `Vazio(props: { children })` — `<div>` com `rounded-xl border border-dashed border-linha p-4 text-sm text-texto`.
  - `Carregando()` — `<div aria-busy="true">` com `<span className="sr-only">Carregando…</span>` e três blocos no formato do card (quadrado 80×80 + duas linhas) em `bg-suave motion-safe:animate-pulse`.

- [ ] **Step 1: Escrever o teste que falha** (acrescentar a `estilos.test.ts`)

```ts
describe("classesCampo", () => {
  it("tem 44px, fundo superficie e borda linha", () => {
    const c = classesCampo(false);
    expect(c).toContain("min-h-11");
    expect(c).toContain("bg-superficie");
    expect(c).toContain("border-linha");
    expect(c).toContain("focus-visible:border-acento");
  });
  it("com erro troca a borda para erro", () => {
    expect(classesCampo(true)).toContain("border-erro");
    expect(classesCampo(true)).not.toContain("border-linha");
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run src/components/ui/estilos.test.ts`
Expected: FAIL — `classesCampo is not a function` (ou erro de import).

- [ ] **Step 3: Implementar `classesCampo`** — `w-full min-h-11 rounded-lg border bg-superficie px-3.5 py-2.5 text-base text-tinta placeholder:text-apagado` + `foco` + `focus-visible:border-acento` + borda por estado. (`text-base` = 16px também evita o zoom automático do iOS ao focar.) A `AreaTexto` usa a mesma string; `min-h-11` não atrapalha `rows`.

- [ ] **Step 4: Rodar e ver passar**

Run: `cd web && npx vitest run src/components/ui/estilos.test.ts`
Expected: PASS.

- [ ] **Step 5: Criar os seis componentes** conforme Interfaces.

- [ ] **Step 6: Verificar**

Run: `cd web && npm test && npm run lint`
Expected: PASS, lint sem erros.

- [ ] **Step 7: Commit**

```bash
git add web/src/components/ui
git commit -m "feat(web): Campo, Seletor, Cartao, Titulo, Vazio e Carregando"
```

---

### Task 4: Cabeçalho e navegação principal

**Files:**
- Create: `web/src/lib/navegacao.ts`
- Test: `web/src/lib/navegacao.test.ts`
- Create: `web/src/components/NavPrincipal.tsx`
- Modify: `web/src/app/layout.tsx`

**Interfaces:**
- Produces:
  - `ITENS_NAV: readonly { href: "/" | "/grupos" | "/conta"; rotulo: "Agenda" | "Grupos" | "Conta" }[]`
  - `itemAtivo(pathname: string, href: string): boolean` — `/` é ativo em `/` e em `/evento/*`; `/grupos` é ativo em `/grupos*` e `/g/*`; `/conta` em `/conta*`; nada em `/entrar`.
  - `NavPrincipal({ variante }: { variante: "topo" | "inferior" })` — `"use client"`, usa `usePathname()`; marca o ativo com `aria-current="page"`.

- [ ] **Step 1: Escrever os testes que falham**

```ts
import { describe, expect, it } from "vitest";
import { itemAtivo } from "./navegacao";

describe("itemAtivo", () => {
  it("Agenda é ativa na raiz e no detalhe do evento", () => {
    expect(itemAtivo("/", "/")).toBe(true);
    expect(itemAtivo("/evento/12", "/")).toBe(true);
    expect(itemAtivo("/grupos", "/")).toBe(false);
  });
  it("Grupos é ativo na lista e na página de um grupo", () => {
    expect(itemAtivo("/grupos", "/grupos")).toBe(true);
    expect(itemAtivo("/g/jazz-em-natal", "/grupos")).toBe(true);
    expect(itemAtivo("/", "/grupos")).toBe(false);
  });
  it("Conta só na conta", () => {
    expect(itemAtivo("/conta", "/conta")).toBe(true);
    expect(itemAtivo("/contato", "/conta")).toBe(false);
  });
  it("nada é ativo em /entrar", () => {
    for (const href of ["/", "/grupos", "/conta"]) expect(itemAtivo("/entrar", href)).toBe(false);
  });
});
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd web && npx vitest run src/lib/navegacao.test.ts`
Expected: FAIL — import não resolvido.

- [ ] **Step 3: Implementar `navegacao.ts`.** Prefixo comparado por segmento (`p === base || p.startsWith(base + "/")`), para `/contato` não casar com `/conta`.

- [ ] **Step 4: Rodar e ver passar**

Run: `cd web && npx vitest run src/lib/navegacao.test.ts`
Expected: PASS (4 testes).

- [ ] **Step 5: Implementar `NavPrincipal` e o layout** (spec §6).
  - `"topo"`: `<nav aria-label="Principal" className="hidden md:flex …">`, links Inter 14px/500; ativo `text-tinta` com sublinhado `decoration-acento decoration-2 underline-offset-[6px]`; inativos `text-apagado`.
  - `"inferior"`: `<nav aria-label="Principal" className="md:hidden fixed inset-x-0 bottom-0 z-20 bg-superficie border-t border-linha pb-[env(safe-area-inset-bottom)]">`, três links `flex-1 flex flex-col items-center justify-center h-14 gap-0.5 text-xs font-medium` com ícone SVG inline 24px (`aria-hidden`, `stroke="currentColor"`, traço 1.75): calendário (Agenda), três pessoas (Grupos), círculo de usuário (Conta). Ativo `text-acento-forte`, inativos `text-apagado`. O nome acessível de cada link continua sendo só o rótulo.
  - `layout.tsx`: `<header className="sticky top-0 z-20 h-14 border-b border-linha bg-fundo/90 backdrop-blur">` com `mx-auto flex h-full max-w-2xl items-center px-4`, wordmark `<Link href="/" className="mr-auto font-serifa text-xl tracking-[-0.01em] text-tinta">Agenda</Link>` e `<NavPrincipal variante="topo" />`. `<main className="mx-auto w-full max-w-2xl flex-1 px-4 py-6 pb-24 md:pb-6">`. `<NavPrincipal variante="inferior" />` depois do `main`.
  - O wordmark "Agenda" e o link "Agenda" da nav têm o mesmo nome; o e2e não procura link "Agenda", então não há conflito.

- [ ] **Step 6: Verificar no navegador**

Run: `cd web && npm run dev` (com a api rodando, conforme o `web/README.md`) e abra `/conta` com viewport 390×844 e depois 1280×800.
Expected: no celular, só o wordmark no topo e a barra embaixo com "Conta" em terracota; no desktop, links no topo e nenhuma barra embaixo; em ambos, o fim da página não fica escondido atrás da barra.

- [ ] **Step 7: Verificar testes e lint**

Run: `cd web && npm test && npm run lint`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add web/src/lib/navegacao.ts web/src/lib/navegacao.test.ts web/src/components/NavPrincipal.tsx web/src/app/layout.tsx
git commit -m "feat(web): cabeçalho fixo e navegação inferior no celular"
```

---

### Task 5: Agenda — `EventoCard`, `ListaPorDia`, `Filtros`, página `/`

**Files:**
- Modify: `web/src/components/EventoCard.tsx`, `web/src/components/ListaPorDia.tsx`, `web/src/app/Filtros.tsx`, `web/src/app/page.tsx`

**Interfaces:**
- Consumes: `Cartao`, `Selo`, `Botao`, `Chip`, `Seletor`, `Titulo`, `Vazio`, `Carregando` (Tasks 2–3); `hora`, `preco`, `selos`, `CATEGORIAS` de `@/lib/formato` (sem mudança).

- [ ] **Step 1: `EventoCard`** (spec §5). `Cartao as="article" className="relative flex gap-3 p-3"`. Flyer `h-20 w-20 flex-none rounded-lg object-cover` (placeholder `bg-suave`). Coluna de texto `min-w-0 flex-1 space-y-1`:
  - selos de `selos(evento)` como `Selo tom="acento"` (todos são alertas: alterado, cancelado, esgotado, adiado);
  - linha `text-[13px] font-medium text-apagado` com a hora em `text-tinta` e o local depois de ` · `;
  - título `h3` `text-base font-semibold leading-snug text-tinta break-words` com `<Link className="after:absolute after:inset-0 after:content-['']">`;
  - linha final `relative z-10 flex flex-wrap items-center gap-3 text-sm`: preço como `Selo tom="acento"` quando for "Grátis", senão texto `text-texto`; "Ingressos →" como `Botao variante="fantasma" tamanho="sm" href externo` com `px-0`.
  O texto do link de ingresso muda de "Ingressos" para "Ingressos →" (o e2e não o usa).

- [ ] **Step 2: `ListaPorDia`.** Rótulo do dia como `h2` `sticky top-14 z-10 bg-fundo py-2 text-xs font-semibold uppercase tracking-[0.08em] text-apagado`; seções com `space-y-2`.

- [ ] **Step 3: `Filtros`.** A função `mudar` não muda.
  - Linha 1: `<div role="group" aria-label="Período" className="flex flex-wrap gap-2">` com `Chip`s.
  - Linha 2: `<div role="group" aria-label="Categoria" className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none]">` com o chip "Todas" (ativo quando `categoria === ""`, chama `mudar({ categoria: "" })`), um `Chip` por entrada de `CATEGORIAS` (clicar no ativo volta para "Todas") e, por último, o chip "Grátis" (`ativo={valores.gratuito}`, alterna `gratuito`).
  - Linha 3: `<Seletor aria-label="Grupo">` com as mesmas `<option>`s, `className="md:w-auto"`.

- [ ] **Step 4: `page.tsx`.** `Titulo nivel={1}` "Agenda"; o estado sem grupos vira `<Vazio>` com o mesmo link (`font-medium text-acento-forte underline`) e o mesmo texto; "Nenhum evento neste período." vira `<Vazio>`; o `Carregando` passa a vir de `@/components/ui/Carregando`.

- [ ] **Step 5: Verificar no navegador (Review Focus 2 e 3)**

Com o dev server, abra `/` em 320×640, 390×844 e 1280×800, em claro e escuro (DevTools → Rendering → `prefers-color-scheme`). Para o caso de dado longo, edite temporariamente o título de um card no DevTools para 80 caracteres sem espaço.
Expected: a linha de categorias rola sozinha e `document.documentElement.scrollWidth === innerWidth` (sem rolagem horizontal na página); o título longo quebra dentro do card; o rótulo do dia fica logo abaixo do cabeçalho ao rolar; clicar em qualquer área do card abre o evento e "Ingressos →" abre o link externo.

- [ ] **Step 6: Verificar testes e lint**

Run: `cd web && npm test && npm run lint`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add web/src/components/EventoCard.tsx web/src/components/ListaPorDia.tsx web/src/app/Filtros.tsx web/src/app/page.tsx
git commit -m "feat(web): agenda com novo card de evento e filtros em chips"
```

---

### Task 6: Página do evento

**Files:**
- Modify: `web/src/app/evento/[id]/page.tsx`

**Interfaces:**
- Consumes: `Titulo`, `Selo`, `Cartao`, `Botao`, `Carregando`.

- [ ] **Step 1: Migrar a página** (spec §7). Flyer `w-full rounded-xl object-contain`; selos como `Selo tom="acento"` numa linha `flex flex-wrap gap-1.5`; título com `Titulo nivel={1}` e `break-words`; dia e hora em `text-texto`; `dl` dentro de `Cartao className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 p-4 text-sm"` com `dt` em `text-apagado` e `dd` em `text-tinta break-words`; "Ingressos" como `Botao variante="primario" href externo className="w-full md:w-auto"`, com o mesmo texto; "Artistas", "Divulgado por" e "Histórico" com `Titulo nivel={2}`; links do Instagram `text-acento-forte underline underline-offset-2`; datas em `text-apagado`; descrição em `text-texto`.

- [ ] **Step 2: Verificar**

Run: `cd web && npm run lint`, depois abra um `/evento/<id>` no dev server em 390×844 claro/escuro.
Expected: lint OK; "Ingressos" de largura total no celular; nenhuma classe `stone-*`/`blue-*` restante (`grep -n "stone-\|blue-" "src/app/evento/[id]/page.tsx"` sem saída).

- [ ] **Step 3: Commit**

```bash
git add "web/src/app/evento/[id]/page.tsx"
git commit -m "feat(web): página do evento com a nova identidade"
```

---

### Task 7: Grupos — lista, novo grupo, página do grupo, editor e seguir

**Files:**
- Modify: `web/src/app/grupos/page.tsx`, `web/src/app/grupos/NovoGrupo.tsx`, `web/src/app/g/[slug]/page.tsx`, `web/src/app/g/[slug]/EditorGrupo.tsx`, `web/src/app/g/[slug]/BotaoSeguir.tsx`

**Interfaces:**
- Consumes: `Titulo`, `Cartao`, `Campo`, `AreaTexto`, `Botao`, `Aviso`, `Vazio`, `Selo`, `Carregando`.

- [ ] **Step 1: `/grupos`.** `Titulo nivel={1}` "Grupos"; `Lista` com `Titulo nivel={2}`; vazio como `<Vazio>`; lista como `Cartao as="ul" className="divide-y divide-linha"` com `li` `px-4 py-3`, link `font-medium text-tinta` e contagem `text-xs text-apagado`.

- [ ] **Step 2: `NovoGrupo`.** `Cartao as="form" onSubmit={criar} className="space-y-3 p-4"`; `Titulo nivel={2}` "Novo grupo"; `<Campo rotulo="Nome" …>` e `<AreaTexto rotulo="Descrição (opcional)" …>` com as mesmas props de hoje; `Botao variante="primario" type="submit"`. O rótulo tem de ser exatamente "Nome" (o e2e usa `getByLabel("Nome", { exact: true })`).

- [ ] **Step 3: `/g/[slug]`.** Nome com `Titulo nivel={1}`; descrição `text-texto`; "Curadoria de …" `text-sm text-apagado`; perfis (visão de quem segue) como `Selo tom="neutro"` com o status em `text-apagado`; "Perfis" e "Próximos eventos" com `Titulo nivel={2}`; "Nenhum evento nos próximos 30 dias." como `<Vazio>`.

- [ ] **Step 4: `BotaoSeguir`.** Sem login: `<Botao variante="primario" href="/entrar">Seguir</Botao>` (vira link, como o e2e espera). Logado: `<Botao variante={sigo ? "secundario" : "primario"} onClick={alternar} disabled={enviando}>`.

- [ ] **Step 5: `EditorGrupo`.** O arquivo tem mudanças da Fatia 2 já commitadas pelo pré-requisito; só troque a apresentação, sem tocar na lógica. Contêiner `Cartao as="section" className="space-y-5 p-4"`; "Editar grupo" com `Titulo nivel={2}`; `Campo`/`AreaTexto` com os mesmos `aria-label` ("Nome do grupo", "Descrição do grupo", "Adicionar @"); "Salvar" e "Adicionar" como `Botao` secundário `type="submit"`; "remover" como `Botao variante="perigo" tamanho="sm"`; "descartar" como `Botao variante="fantasma" tamanho="sm"`; bloco "Para confirmar" `rounded-lg bg-suave p-3`; motivos de recusa em `text-erro`; status do perfil em `text-apagado`; "Confirmar (n)" como `Botao variante="primario"`; ações finais com as variantes equivalentes (excluir = `perigo`). Todos os textos permanecem iguais.

- [ ] **Step 6: Verificar**

Run: `cd web && npm run lint && grep -rn "campos\"\|stone-\|red-\|blue-" src/app/grupos "src/app/g"`
Expected: lint OK; o grep não imprime nada.

- [ ] **Step 7: Commit**

```bash
git add web/src/app/grupos "web/src/app/g"
git commit -m "feat(web): grupos e página pública com a nova identidade"
```

---

### Task 8: Entrar, Conta e limpeza

**Files:**
- Modify: `web/src/app/entrar/page.tsx`, `web/src/app/entrar/FormularioEntrar.tsx`, `web/src/app/conta/page.tsx`, `web/src/app/conta/BotaoSair.tsx`
- Delete: `web/src/components/campos.ts`, `web/src/components/Aviso.tsx`, `web/src/components/Carregando.tsx`

**Interfaces:**
- Consumes: `Titulo`, `Cartao`, `Campo`, `Botao`, `Aviso`, `Carregando`.

- [ ] **Step 1: `/entrar`.** Página `mx-auto max-w-sm space-y-4 pt-4 md:pt-10`; `Titulo nivel={1}` "Entrar"; `FormularioEntrar` dentro de `Cartao className="p-6"`. No formulário: `<Campo rotulo="E-mail" …>`, `<Campo rotulo="Código de convite" …>`, `<Campo rotulo="Seu nome" …>` com as mesmas props; o parágrafo do convite em `text-sm text-texto`; botão `Botao variante="primario" type="submit" className="w-full"` com os mesmos três textos. A mensagem "Enviamos um link…" continua um `Aviso tipo="info"`.

- [ ] **Step 2: `/conta`.** `Titulo nivel={1}` "Conta"; `dl` dentro de `Cartao className="space-y-3 p-4 text-sm"` com `dt` `text-apagado` e `dd` `text-tinta`; `BotaoSair` como `<Botao onClick={sair}>Sair</Botao>` (secundário).

- [ ] **Step 3: Trocar os imports restantes e apagar os antigos.** Todo `@/components/Aviso` passa a `@/components/ui/Aviso`, e todo `@/components/Carregando` a `@/components/ui/Carregando`; apague os três arquivos listados.

- [ ] **Step 4: Verificar a limpeza**

Run: `cd web && grep -rnE "(stone|blue|amber|red|emerald)-[0-9]|components/campos|components/(Aviso|Carregando)\"" src`
Expected: nenhuma saída.

- [ ] **Step 5: Verificar testes, lint e build**

Run: `cd web && npm test && npm run lint && npx next build`
Expected: tudo sem erro.

- [ ] **Step 6: Commit**

```bash
git add -A web/src/app/entrar web/src/app/conta web/src/components
git commit -m "feat(web): entrar e conta na nova identidade; remove estilos antigos"
```

---

### Task 9: Verificação final (e2e e revisão visual)

**Files:**
- Nenhum arquivo de produto. Capturas no diretório de rascunho da sessão (não commitar).

- [ ] **Step 1: Rodar o smoke**

Run: `cd web && npm run e2e` (precisa do Postgres, do SeaweedFS e do Mailpit do `docker-compose.yml` no ar)
Expected: `1 passed`. O `playwright.config.ts` já usa `devices["Pixel 7"]` (celular), então este passo cobre a navegação inferior; a verificação de 390×844 da spec §8 fica atendida sem config extra. Se falhar por seletor, o erro está no componente (texto, rótulo ou `role` alterado), não no teste: corrija o componente.

- [ ] **Step 2: Capturas para revisão**

Com o dev server e dados de exemplo, capture `/entrar`, `/`, `/evento/<id>`, `/grupos`, `/g/<slug>` (logado como dono e deslogado) e `/conta`, nas combinações claro/escuro × 390×844/1280×800. Em pelo menos uma tela por tema, capture também um campo com foco por teclado, um botão primário desabilitado e um aviso de erro (Review Focus 5).
Expected: o conjunto de imagens é mostrado à pessoa para revisão antes de encerrar o branch; ajustes pedidos viram commits `fix(web): …` e repetem os Steps 1–2.
