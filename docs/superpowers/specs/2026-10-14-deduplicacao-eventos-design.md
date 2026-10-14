# Deduplicação de eventos e agrupamento de festivais — Design

Complementa `2026-10-09-agenda-cultural-instagram-design.md` (seções 3.5, 3.6 e 4). Onde
as duas divergirem, vale esta.

## 1. Problema

Depois da Fatia 1, a coleta real de três perfis (`festivalmada`, `festivaldosol`,
`jazznobardenazare`) gerou 74 eventos com duplicatas visíveis:

- o mesmo festival com títulos diferentes no mesmo dia ("MADA — Música Alimento da
  Alma", "Festival MADA 2026 - Dia 1", "Festival MADA 2026 - Sexta do MADA"…);
- cada atração de festival como evento próprio ("Baile da Amada com Belisa", "Show do
  Zeca Pagodinho no Festival MADA 2026", "Show do Siba" e "Siba no Festival DoSol");
- a identidade do evento decidida pelo modelo de reconciliação, que varia e erra.

## 2. Objetivo e critérios de sucesso

1. **Nome parecido na mesma data é o mesmo evento**, sem depender do modelo.
2. **Atração de festival é o festival.** Shows, bailes e apresentações que fazem parte de
   um festival viram **um evento do festival por dia**; as atrações entram em `artistas`
   e na descrição, e os posts delas viram fontes do evento do festival.
3. **Duplicatas que já existem são fundidas**, por comando e automaticamente no worker.

Aceite: reprocessados os 134 posts, (a) nenhum par de eventos no mesmo dia com nome
parecido; (b) MADA aparece como um evento em 16/10 e outro em 17/10; (c) DoSol aparece
como um evento por dia de festival; (d) a turnê do Jambu continua um evento por cidade e
os shows avulsos (Jáder, Giovanna Moraes, Black Pantera na Sede Dosol) continuam
próprios; (e) golden set e testes passando.

Fora do escopo: front, eventos que atravessam a meia-noite, festival como um único
evento de vários dias.

## 3. Extração: campo `festival` e agrupamento

### 3.1 Schema

`EventoExtraido` ganha `festival: str | None` (obrigatório e anulável, como os demais,
por causa dos structured outputs estritos). Regra no prompt:

> `festival` é o nome do festival ou evento maior de que este evento faz parte
> ("Festival MADA 2026", "Festival DoSol 2026"), quando o post diz isso; senão, null.
> Para o próprio festival (o post anuncia o festival, não uma atração), `festival` é o
> nome dele também.

### 3.2 Agrupamento (`extracao/regras.py`, `agrupar_festivais`)

Função pura, aplicada **na reconciliação** depois de `filtrar_validos` (a extração bruta
fica salva em `posts.extracao`, sem agrupamento, para auditoria e reprocessamento):

- eventos com `festival` são agrupados por `(nome normalizado do festival, data_inicio)`;
- cada grupo vira **um** `EventoExtraido`:
  - `titulo` = `festival` (a grafia do primeiro do grupo);
  - `festival` = o mesmo nome;
  - `artistas` = união, sem repetição (normalizada), na ordem em que aparecem;
  - `local_nome`, `endereco`, `cidade`: o valor se todos os preenchidos coincidirem
    (comparação normalizada); senão, null;
  - `hora_inicio` = a mais cedo entre as definidas; `hora_fim` = a mais tarde;
    `data_fim` = null;
  - `descricao` = uma linha por atração: `titulo` original, e `local_nome`/hora quando
    houver;
  - `categoria` = `festival`;
  - preço: menor `preco_min` e maior `preco_max`; `gratuito` = true só se todos forem;
    `link_ingresso` e `preco_texto` = o primeiro preenchido;
  - `status_indicado`: `cancelado` ou `adiado` só se todos tiverem; `esgotado` se algum
    tiver; senão, null;
  - `confianca`: a menor de cada campo.
- eventos sem `festival` passam intactos.

`avaliar --etapa extracao` passa a pontuar a saída agrupada.

## 4. Identidade determinística (`reconciliacao/identidade.py`)

### 4.1 Normalização

- `normalizar(texto)`: minúsculas, sem acento, pontuação vira espaço, espaços
  colapsados.
- `tokens(texto)`: tokens de `normalizar`, sem palavras vazias (`a o as os de da do das
  dos e em no na nos nas com para pra por`).
- `cidade_norm(c)`: `normalizar` da parte antes de `/` ou `-` ("ARACAJU/SE" → "aracaju",
  "Natal/RN" → "natal").

### 4.2 `nomes_parecidos(a, b)`

Verdadeiro se, com `ta = tokens(a)` e `tb = tokens(b)` não vazios:
- `normalizar(a) == normalizar(b)`; ou
- `ta ⊆ tb` ou `tb ⊆ ta`; ou
- `SequenceMatcher(normalizar(a), normalizar(b)).ratio() >= 0.8`.

### 4.3 `mesmo_evento(a, b)`

`a` e `b` são eventos (gravados ou o candidato a gravar). São o mesmo evento se **todas**
as condições valem:
1. mesmo dia em `America/Sao_Paulo`;
2. `nomes_parecidos(a.titulo, b.titulo)` **ou** (os dois têm `festival` e
   `nomes_parecidos(a.festival, b.festival)`);
3. **não** têm cidades diferentes: se as duas `cidade` estão preenchidas,
   `cidade_norm` é igual;
4. **não** têm horários conflitantes: se os dois têm `hora_definida` e algum deles não
   tem `festival`, o `inicio` é igual.

Não exige local nem artistas. A condição 3 separa turnês (Jambu em Aracaju × Salvador) e
edições do mesmo festival em cidades diferentes; a 4 separa sessões no mesmo dia. A 4 não
vale entre dois eventos de festival, porque a hora de um festival agrupado é a da
primeira atração que cada post cita e varia de post para post.

## 5. Modelo de dados

`eventos` ganha `festival text null` (migração `0002`), com índice `pg_trgm`. É gravado
a partir de `EventoExtraido.festival`, entra no mapeamento de `campos_do_evento` e é
preenchível por DUPLICADO como os demais campos.

## 6. Busca de candidatos (Etapa B)

Além dos critérios atuais, a busca **sempre** inclui os eventos do mesmo dia cujo
`titulo` (ou `festival`) tenha similaridade `pg_trgm` ≥ 0,3 com o título (ou festival)
extraído, até 10 deles, antes de completar com os demais critérios até o limite total
(que sobe de 5 para 10). Assim o par certo não fica de fora quando há muitos títulos
parecidos em outras datas (caso "Festival Dosol 2026", com 28 eventos semelhantes).

## 7. Reconciliação (Etapa C)

Para cada evento (já agrupado) do post:

1. busca os candidatos;
2. **pares fortes** = candidatos de **outro** post com `mesmo_evento(extraído,
   candidato)`; se houver mais de um, o par é o de mais fontes (empate: menor id);
3. com par forte, o modelo recebe **só esse candidato** e a decisão `NOVO` é inválida
   (vale a retentativa existente; esgotadas as tentativas, aplica-se `DUPLICADO`);
4. sem par forte, o fluxo segue como hoje (o modelo vê todos os candidatos e pode
   responder `NOVO`);
5. `aplicar` segue com as regras atuais (R23, R30, ATUALIZACAO que só preenche vira
   DUPLICADO). O `_casamento_forte` atual é substituído pelo passo 2.

## 8. Fusão de duplicatas existentes

### 8.1 `fundir(s, manter, remover, motivo)` (`reconciliacao/fusao.py`)

Numa savepoint:
- move as `evento_fontes` de `remover` para `manter` (se o par `(manter, post)` já
  existe, descarta a de `remover`);
- move as `revisoes_evento` de `remover` para `manter`;
- preenche campos vazios de `manter` com os de `remover` (mesma regra de DUPLICADO,
  incluindo acrescentar a hora no mesmo dia), gerando revisões com o `motivo`;
- `artistas` = união; `status` de `manter` só muda se estiver `ativo` e o outro não;
- apaga `remover`.

`manter` é o evento com mais fontes (empate: menor id).

### 8.2 Varredura (`deduplicar(s, eventos=None)`)

Agrupa por dia os eventos de `inicio` futuro (ou até 7 dias atrás); dentro de cada dia,
funde em cadeia os pares com `mesmo_evento` até não haver mais. Com `eventos`, varre só
os dias desses eventos. Devolve a lista de fusões `(manter, remover)`.

### 8.3 Onde roda

- **CLI** `agenda deduplicar [--aplicar]`: sem `--aplicar`, só lista o que fundiria
  (simulação, sem alterar o banco); com `--aplicar`, funde e lista.
- **Worker**: ao fim de `tratar_reconciliar_post`, `deduplicar(s, eventos tocados pelo
  post)`, na mesma transação. Cada fusão é registrada no log em nível WARNING.

## 9. Testes e medição

- Unidade: `agrupar_festivais` (lineup de 2 dias vira 2 eventos; união de artistas;
  locais divergentes viram null; evento sem festival intacto), `nomes_parecidos`,
  `mesmo_evento` (contraexemplos: cidades diferentes, outro dia, horários definidos
  diferentes), `fundir` (fontes, revisões, conflito de fonte, preenchimento, artistas,
  status), `deduplicar` (cadeia de 3 duplicatas no mesmo dia), reconciliação com par
  forte (modelo só vê o par; `NOVO` rejeitado).
- Golden: `mada_lineup` passa a esperar 2 eventos (16 e 17/10, título do festival,
  artistas do lineup); novos casos de atração dentro de festival (Siba no DoSol, Baile da
  Amada no MADA) e de reconciliação entre variações de título do mesmo festival.
- Aceite: os critérios da seção 2 sobre os 134 posts reprocessados, conferidos com
  `agenda deduplicar` (simulação vazia) e `agenda eventos`.
