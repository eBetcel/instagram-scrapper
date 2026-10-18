# Identidade visual e componentes do front — Design

Complementa `2026-10-14-fatia-2-produto-web-design.md`. Referência de linguagem visual:
`DESIGN.md` na raiz (gerado por `npx getdesign add claude`). Onde divergirem, vale esta.

## 1. Objetivo e contexto

Dar ao front web (`web/`) uma identidade visual moderna e própria, e uma base pequena de
componentes reutilizáveis, para o **piloto com pessoas reais**, que usam a agenda
principalmente no celular.

Inspiração: a linguagem do `DESIGN.md` (canvas creme quente, serifa nos títulos, um único
acento quente, profundidade por cor e não por sombra). **Não** usamos marca, logo
(asterisco) nem nome da Anthropic/Claude: a Agenda tem cara própria.

Sucesso:
1. As seis telas (`/entrar`, `/`, `/evento/[id]`, `/grupos`, `/g/[slug]`, `/conta`) usam
   só os tokens e os componentes desta spec; nenhuma classe `stone-*`, `blue-*`,
   `amber-*`, `red-*` ou `emerald-*` sobra em `web/src`.
2. Modo escuro automático (segue o sistema) funciona em todas as telas.
3. No celular (< 768px) há navegação inferior fixa; no desktop, links no cabeçalho.
4. Contraste AA em texto; botões, campos e itens de navegação com pelo menos 44px de
   altura (chips de filtro: 36px).
5. `npm test`, `npm run lint`, `next build` e `npm run e2e` passam **sem alterar
   seletores do e2e**.

Fora do escopo: logo/favicon, animações e transições, alternador manual de tema,
mudanças no backend, mudanças de rota, de texto ou de funcionalidade.

## 2. Abordagem

Tokens como variáveis CSS expostas ao Tailwind 4 via `@theme` em `globals.css`, e ~10
componentes próprios em `web/src/components/ui/`. Sem dependências novas de runtime nem
de teste. `web/src/components/campos.ts` é removido.

Alternativas descartadas: só trocar classes (variantes continuariam espalhadas como
strings) e shadcn/ui (dependências e código gerado demais para seis telas, visual mais
genérico).

## 3. Tokens

### 3.1 Cores

Definidas em `:root` e redefinidas em `@media (prefers-color-scheme: dark)`. Expostas no
`@theme` como `--color-<nome>`, gerando utilitários `bg-fundo`, `text-tinta`,
`border-linha` etc.

| Token          | Claro     | Escuro    | Uso                                                       |
|----------------|-----------|-----------|-----------------------------------------------------------|
| `fundo`        | `#faf8f3` | `#181715` | fundo da página                                           |
| `superficie`   | `#fdfbf7` | `#211f1c` | cards, campos, navegação inferior                         |
| `suave`        | `#f1ebe0` | `#2a2824` | selos neutros, esqueletos, placeholder de flyer           |
| `linha`        | `#e6dfd5` | `#35322d` | bordas de 1px, divisórias                                 |
| `tinta`        | `#1c1a17` | `#f5f1ea` | títulos, texto principal                                  |
| `texto`        | `#3d3a35` | `#d6d1c8` | texto corrido                                             |
| `apagado`      | `#6c6860` | `#9e998f` | hora, local, legendas, rótulos de dia                     |
| `acento`       | `#b4532f` | `#de7a58` | fundo do botão primário, borda/anel de foco               |
| `acento-forte` | `#a64c2e` | `#ec9070` | links e texto em acento; botão primário pressionado        |
| `erro`         | `#b93c3c` | `#e57373` | avisos de erro, ação de perigo                            |
| `sucesso`      | `#37704a` | `#7fbf8f` | avisos de sucesso/info                                    |

Regra de contraste: texto pequeno ou link em acento usa sempre `acento-forte`. O `acento`
puro só aparece como fundo do botão primário (texto branco, 14px/600) e em bordas/anéis.
No escuro, o botão primário usa texto `#181715` sobre `acento`.

### 3.2 Tipografia

Carregadas por `next/font/google` (auto-hospedadas), expostas como `--font-serifa`
(Fraunces) e `--font-sans` (Inter); Inter é a fonte do `body`.

| Papel             | Fonte    | Tamanho / peso / espaçamento        |
|-------------------|----------|-------------------------------------|
| h1 da página      | Fraunces | 30px (32px ≥ 768px) / 400 / −0,02em |
| h2 de seção       | Fraunces | 20px / 400 / −0,01em                |
| título do evento (detalhe) | Fraunces | 30px / 400 / −0,02em       |
| título no card    | Inter    | 16px / 600                          |
| corpo             | Inter    | 15–16px / 400 / altura 1,55         |
| rótulo, botão     | Inter    | 13–14px / 500–600                   |
| rótulo de dia     | Inter    | 12px / 600 / caixa alta / 0,08em    |

### 3.3 Forma, espaço e foco

- Raios: 8px (botões, campos, flyer no card), 12px (cards, flyer no detalhe), pílula
  (selos, chips).
- Sombra: só `0 1px 3px rgb(20 20 19 / 0.06)` no `Cartao`; no escuro, nenhuma.
- Espaçamento em múltiplos de 4px; largura de conteúdo continua `max-w-2xl`.
- Foco: `focus-visible` com anel sólido de 2px em `acento-forte` e offset de 2px na cor `fundo`; campos também com borda `acento`.

## 4. Componentes base (`web/src/components/ui/`)

Cada componente com variantes expõe também uma função pura que devolve as classes
(ex.: `classesBotao`), testada no Vitest.

- **`Botao`** — props: `variante` (`primario` | `secundario` | `fantasma` | `perigo`,
  padrão `secundario`), `tamanho` (`md` | `sm`, padrão `md`), e as props nativas. Com
  `href`, renderiza `next/link` (rota interna) ou `<a>` (URL externa, com
  `target="_blank" rel="noopener noreferrer"` quando `externo`). `md`: altura mínima
  44px, padding 0 16px, raio 8px. `primario`: `bg-acento` + texto branco (escuro: texto
  `fundo`), `active:` escurece para `acento-forte`. `secundario`: `bg-superficie`,
  borda `linha`, texto `tinta`. `fantasma`: sem fundo, texto `acento-forte`. `perigo`:
  sem fundo, texto `erro`. `disabled`: 50% de opacidade, cursor padrão.
- **`Campo`** e **`AreaTexto`** — props nativas + `rotulo?` e `erro?`. Altura mínima 44px
  (campo), padding 10px 14px, `bg-superficie`, borda `linha`, raio 8px, foco com borda
  `acento` + anel. Com `rotulo`, renderiza `<label>` visível (13px/500, `texto`) ligado
  por `id` (gerado com `useId` se ausente). Sem `rotulo`, o chamador passa `aria-label`.
  Com `erro`, borda `erro` e mensagem abaixo ligada por `aria-describedby`.
- **`Seletor`** — `<select>` nativo com o mesmo visual de `Campo` e uma seta SVG.
- **`Cartao`** — prop `as` (padrão `div`) e `className`. `bg-superficie`, borda `linha`,
  raio 12px, sombra da 3.3.
- **`Selo`** — prop `tom` (`neutro` | `acento`). Pílula, 12px/500, padding 2px 10px.
  `neutro`: `bg-suave text-texto`. `acento`: texto `acento-forte` sobre `acento` a 12%.
- **`Chip`** — props `ativo`, `onClick` ou `href`. Botão em pílula, altura mínima 36px,
  padding 0 14px, 14px/500, `aria-pressed={ativo}`.
  Inativo: borda `linha`, texto `texto`. Ativo: `bg-tinta text-fundo`, borda `tinta`.
- **`Aviso`** — prop `tipo` (`erro` | `info` | `sucesso`). Mantém `role="alert"` para
  erro e `role="status"` para os demais. Fundo da cor do tipo a 8%, borda a 25%, texto
  na cor do tipo.
- **`Titulo`** — prop `nivel` (1 | 2) e `className`; aplica os estilos de 3.2.
- **`Vazio`** — estado vazio: borda tracejada `linha`, raio 12px, padding 16px, texto
  `texto`, 14px.
- **`Carregando`** — três esqueletos do formato do card de evento, pulsando em `suave`
  (`motion-safe:animate-pulse`), contêiner com `aria-busy="true"` e texto
  "Carregando…" visível só para leitores de tela.

## 5. Componentes de domínio

- **`EventoCard`** — `Cartao as="article"` com padding 12px e `relative`. Flyer 80×80
  (raio 8px; placeholder `bg-suave`). Ordem do texto: selos (`Selo`; "Grátis" e
  equivalentes em `acento`, demais `neutro`); linha "hora · local · cidade" (13px/500,
  hora em `tinta`, resto em `apagado`); título (Inter 16px/600) como `Link` cujo
  `::after` cobre o card (card todo clicável); linha final com preço e
  `Botao variante="fantasma" tamanho="sm" externo` "Ingressos →", posicionado acima do
  `::after` (`relative z-10`). O nome acessível do link continua sendo só o título.
- **`ListaPorDia`** — rótulo do dia (3.2) `sticky` logo abaixo do cabeçalho, com
  `bg-fundo` e padding vertical 8px.
- **`Filtros`** — linha 1: `Chip`s de período (grupo com `aria-label="Período"`). Linha
  2: `Chip`s de categoria ("Todas" + `CATEGORIAS`) mais o chip "Grátis" (substitui o
  checkbox "Só gratuitos"), com `overflow-x-auto` e sem quebra de linha no celular (grupo
  com `aria-label="Categoria"`). Linha 3: `Seletor` de grupo, com `aria-label="Grupo"`.
  A lógica de URL (`mudar`) não muda.

## 6. Layout e navegação

- **`layout.tsx`** — carrega as fontes; `body` com `bg-fundo text-texto font-sans`.
  Cabeçalho `sticky top-0` de 56px, `bg-fundo/90` com `backdrop-blur`, borda inferior
  `linha`. Wordmark "Agenda" em Fraunces 20px, `text-tinta`, link para `/`.
- **`NavPrincipal`** (cliente, `usePathname`) — itens Agenda (`/`), Grupos (`/grupos`) e
  Conta (`/conta`); ativo por igualdade (`/`) ou prefixo (demais), com
  `aria-current="page"`.
  - Desktop (≥ 768px): no cabeçalho, à direita, Inter 14px/500; ativo em `tinta` com
    sublinhado `acento` de 2px; inativos em `apagado`.
  - Celular (< 768px): barra fixa inferior, `bg-superficie`, borda superior `linha`,
    três itens de 56px de altura com ícone SVG inline (24px) e rótulo 12px/500; ativo em
    `acento-forte`, inativos em `apagado`; `padding-bottom: env(safe-area-inset-bottom)`.
  - A variante oculta usa `hidden`/`md:flex` (`display:none`), então cada viewport tem um
    único link visível por destino.
- **`main`** — `pb-24` no celular (`md:pb-6`) para a barra não cobrir o conteúdo.
- O layout continua sem ler sessão nem cookies (regra do `cacheComponents`).

## 7. Telas

Todas trocam `h1`/`h2` por `Titulo`, botões por `Botao`, campos por `Campo`/`AreaTexto`/
`Seletor`, caixas por `Cartao`, mensagens por `Aviso` e vazios por `Vazio`.

- **`/entrar`** — formulário dentro de um `Cartao` (padding 24px), centralizado, com
  título da página em Fraunces e botão primário de largura total.
- **`/`** — `Filtros`, `ListaPorDia`; "Crie um grupo…" e "Nenhum evento neste período."
  como `Vazio`.
- **`/evento/[id]`** — flyer com raio 12px; selos como `Selo`; título em Fraunces 30px;
  dia e hora em `texto`; `dl` dentro de `Cartao` (`dt` em `apagado`); "Ingressos" como
  `Botao primario` de largura total no celular; seções com `Titulo nivel={2}`; links do
  Instagram em `acento-forte`.
- **`/grupos`** — listas de grupos num `Cartao` com `divide-y divide-linha`, item com
  padding 12px 16px; `NovoGrupo` com `Campo` e `Botao primario`.
- **`/g/[slug]`** — cabeçalho do grupo (nome em Fraunces, "Curadoria de…" em `apagado`),
  `BotaoSeguir` como `Botao` (primário para "Seguir", secundário para "Deixar de
  seguir"); `EditorGrupo` num `Cartao`; ações de remover/descartar como `fantasma` ou
  `perigo`; bloco "Para confirmar" com `bg-suave`.
- **`/conta`** — dados num `Cartao`; "Sair" como `Botao secundario`.

Nenhum texto visível, rótulo, `aria-label` ou `role` usado em `web/e2e/piloto.spec.ts`
muda.

## 8. Testes e verificação

- **Vitest** (sem dependências novas): funções puras de classes (`classesBotao`,
  `classesChip`, `classesSelo`, `classesAviso`) e a regra de item ativo da
  `NavPrincipal` (função pura `itemAtivo(pathname, href)`).
- **Playwright:** `npm run e2e` passa sem alterar seletores. A navegação inferior é
  verificada uma vez rodando o smoke com viewport 390×844 (via `--project` temporário ou
  `use.viewport` local, sem commitar), porque o smoke cria usuários e grupos fixos e não
  pode rodar duas vezes na mesma carga do banco.
- **Lint e build:** `npm run lint` e `next build` sem erros.
- **Revisão visual:** capturas das seis telas em claro/escuro × celular/desktop,
  revisadas pela pessoa antes do commit final.

## 9. Emendas (2026-10-18, revisão final)

- `acento` claro passou de `#c8613f` para `#b4532f` e `sucesso` claro de `#3f7a52` para `#37704a`: com os valores
  originais, o texto branco do botão primário (~4,0:1) e o aviso de sucesso (~4,35:1) ficavam abaixo de AA, o que
  violava o critério de sucesso 4.
- O anel de foco passou a ser sólido (`acento-forte`, 2px, offset 2px): o anel de 25% ficava em ~1,35:1 e era
  quase invisível em botões, chips e links da navegação.
- O botão primário usa peso 600 (`font-semibold`); os demais botões, 500.
