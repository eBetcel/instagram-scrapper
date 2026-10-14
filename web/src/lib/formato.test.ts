import { describe, expect, it } from "vitest";
import { hora, preco, selos } from "./formato";
import type { Evento } from "./tipos";

const base = {
  inicio: "2026-10-19T00:00:00Z", hora_definida: true, gratuito: null, preco_min: null,
  preco_max: null, preco_texto: null, status: "ativo", alterado: false,
} as unknown as Evento;
const ev = (kw: Partial<Evento>) => ({ ...base, ...kw }) as Evento;

describe("formato", () => {
  it("hora no fuso de São Paulo ou a confirmar", () => {
    expect(hora(ev({}))).toBe("21:00");
    expect(hora(ev({ hora_definida: false }))).toBe("horário a confirmar");
  });

  it("preço", () => {
    expect(preco(ev({ gratuito: true }))).toBe("Grátis");
    expect(preco(ev({ preco_max: "0.00" }))).toBe("Grátis");
    expect(preco(ev({ preco_min: "40.00", preco_max: "40.00" }))).toBe("R$ 40");
    expect(preco(ev({ preco_min: "30.00", preco_max: "60.50" }))).toBe("R$ 30 a R$ 60,50");
    expect(preco(ev({ preco_texto: "Contribuição consciente" }))).toBe("Contribuição consciente");
    expect(preco(ev({}))).toBeNull();
  });

  it("selos na ordem alterado, cancelado, esgotado, adiado", () => {
    expect(selos(ev({}))).toEqual([]);
    expect(selos(ev({ alterado: true, status: "esgotado" }))).toEqual(["⚠️ alterado", "🔴 esgotado"]);
    expect(selos(ev({ status: "cancelado" }))).toEqual(["❌ cancelado"]);
    expect(selos(ev({ status: "adiado" }))).toEqual(["⏸ adiado"]);
  });
});
