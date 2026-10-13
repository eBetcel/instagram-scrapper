# Golden set

Casos reais anotados à mão para medir a qualidade da extração (Etapa B) e da
reconciliação (Etapa C). Meta: cerca de 50 casos em `backend/golden/casos/`.

## Rodar

    cd backend
    uv run agenda avaliar --etapa extracao --golden golden/casos
    uv run agenda avaliar --etapa reconciliacao --golden golden/casos

Chama a OpenAI de verdade (precisa de `OPENAI_API_KEY`) e imprime o relatório com o
custo total. Não faz parte do `pytest` nem do CI.

## Layout de um caso

    golden/casos/<nome_do_caso>/
        legenda.txt      # legenda do post (opcional; vazio se ausente)
        imagem1.jpg      # zero ou mais imagens `imagem*.jpg`, em ordem alfabética
        imagem2.jpg
        esperado.json

## `esperado.json`

    {
      "username": "casax",
      "publicado_em": "2026-10-06T12:00:00-03:00",
      "eventos": [
        {"titulo": "Rock na Casa X", "data_inicio": "2026-10-10", "hora_inicio": "21:00:00",
         "cidade": "São Paulo", "categoria": "show", "artistas": ["Banda A"],
         "preco_min": 40.0, "preco_max": 40.0}
      ],
      "reconciliacao": {
        "candidatos": [{"id": 7, "titulo": "Show da Banda A",
                        "inicio": "2026-10-10T21:00:00-03:00", "categoria": "show",
                        "artistas": ["Banda A"]}],
        "evento": 0,
        "decisao_esperada": "ATUALIZACAO",
        "evento_id_esperado": 7
      }
    }

- `eventos`: lista de eventos esperados, no formato de `EventoExtraido`. Anote **só os
  campos que quer avaliar**; campos ausentes não entram na nota. Campos pontuados:
  `titulo`, `data_inicio`, `hora_inicio`, `cidade`, `categoria`, `artistas`,
  `preco_min`, `preco_max`. Post sem eventos: `"eventos": []`.
- `reconciliacao` (opcional): só os casos com esse bloco entram na avaliação da
  reconciliação. `candidatos` são os eventos já cadastrados (campos de `Evento`; `id`
  obrigatório, `inicio` em ISO com fuso); `evento` é o índice em `eventos` do evento a
  reconciliar; `decisao_esperada` é `NOVO`, `DUPLICADO` ou `ATUALIZACAO`;
  `evento_id_esperado` é o `id` do candidato correto, ou `null` para `NOVO`.

## Como a nota é calculada (extração)

- Cada evento esperado é pareado com o evento extraído ainda livre de mesma
  `data_inicio` e maior similaridade de título (senão, o de maior similaridade geral).
  Esperado sem par conta como errado em todos os campos.
- `titulo`: similaridade (`difflib`, sem acento e minúsculas) >= 0,8.
  `data_inicio`, `hora_inicio`, `cidade`, `categoria`: igualdade exata.
  `artistas`: F1 sobre nomes normalizados. `preco_min`/`preco_max`: tolerância zero.
- O relatório mostra a acurácia por campo e a contagem de eventos esperados vs
  extraídos, por caso e no total.

## Casos mínimos a cobrir

1. Flyer com várias datas (programação mensal).
2. Adiamento.
3. Cancelamento.
4. Mesmo show divulgado pela casa e pelo artista.
5. Mesmo título em locais diferentes.
6. Post de dezembro com data de janeiro.
7. Post só com legenda (sem imagem).
