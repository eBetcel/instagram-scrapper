import { describe, expect, it } from "vitest";
import { adicionarPendente, restantes } from "./pendentes";

describe("pendentes", () => {
  it("normaliza o @ e ignora vazio e repetido", () => {
    let lista: string[] = [];
    lista = adicionarPendente(lista, "  @CasaX ");
    lista = adicionarPendente(lista, "casax");
    lista = adicionarPendente(lista, "@");
    lista = adicionarPendente(lista, "   ");
    expect(lista).toEqual(["casax"]);
  });

  it("não altera a lista recebida", () => {
    const lista = ["a"];
    adicionarPendente(lista, "b");
    expect(lista).toEqual(["a"]);
  });

  it("depois do envio sobram só os recusados, com o motivo", () => {
    const pendentes = ["boa", "ruim!", "outra"];
    const resultados = [
      { username: "boa", status: "coletando", erro: null },
      { username: "ruim!", status: null, erro: "@ inválido" },
      { username: "outra", status: "ativo", erro: null },
    ] as const;
    expect(restantes(pendentes, [...resultados])).toEqual([{ username: "ruim!", erro: "@ inválido" }]);
  });
});
