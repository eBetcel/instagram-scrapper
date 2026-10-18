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
