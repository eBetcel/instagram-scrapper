import { describe, expect, it } from "vitest";
import { agruparPorDia, diaDe, intervalo, rotuloDia } from "./datas";
import type { Evento } from "./tipos";

// Domingo 18/10 às 23h30 em São Paulo (segunda 19/10 02h30 em UTC).
const DOMINGO_NOITE = new Date("2026-10-19T02:30:00Z");
const SEGUNDA = new Date("2026-10-19T18:00:00Z"); // 15h em SP
const SABADO = new Date("2026-10-17T15:00:00Z");

describe("intervalo", () => {
  it("usa o dia de São Paulo, não o do relógio em UTC", () => {
    expect(intervalo("hoje", DOMINGO_NOITE)).toEqual({ de: "2026-10-18", ate: "2026-10-18" });
    expect(intervalo("fim-de-semana", DOMINGO_NOITE)).toEqual({ de: "2026-10-17", ate: "2026-10-18" });
  });

  it("numa segunda, fim de semana é o próximo", () => {
    expect(intervalo("fim-de-semana", SEGUNDA)).toEqual({ de: "2026-10-24", ate: "2026-10-25" });
  });

  it("num sábado, fim de semana é hoje e amanhã", () => {
    expect(intervalo("fim-de-semana", SABADO)).toEqual({ de: "2026-10-17", ate: "2026-10-18" });
  });

  it("semana e mês", () => {
    expect(intervalo("semana", SEGUNDA)).toEqual({ de: "2026-10-19", ate: "2026-10-25" });
    expect(intervalo("mes", SEGUNDA)).toEqual({ de: "2026-10-19", ate: "2026-10-31" });
    expect(intervalo("mes", new Date("2026-12-31T12:00:00Z"))).toEqual({ de: "2026-12-31", ate: "2026-12-31" });
  });

  it("próximos cobre 60 dias, atravessando mês e ano", () => {
    expect(intervalo("proximos", DOMINGO_NOITE)).toEqual({ de: "2026-10-18", ate: "2026-12-17" });
    expect(intervalo("proximos", new Date("2026-12-31T12:00:00Z"))).toEqual({ de: "2026-12-31", ate: "2027-03-01" });
  });
});

describe("dias", () => {
  it("diaDe converte para São Paulo", () => {
    expect(diaDe("2026-10-19T02:30:00Z")).toBe("2026-10-18");
    expect(diaDe("2026-10-19T03:30:00Z")).toBe("2026-10-19");
  });

  it("agruparPorDia separa 23h30 de 00h30 e mantém a ordem", () => {
    const ev = (id: number, inicio: string) => ({ id, inicio }) as Evento;
    const grupos = agruparPorDia([ev(1, "2026-10-19T02:30:00Z"), ev(2, "2026-10-19T03:30:00Z"), ev(3, "2026-10-19T20:00:00Z")]);
    expect(grupos.map((g) => [g.dia, g.eventos.map((e) => e.id)])).toEqual([
      ["2026-10-18", [1]],
      ["2026-10-19", [2, 3]],
    ]);
  });

  it("rotuloDia", () => {
    expect(rotuloDia("2026-10-18", "2026-10-18")).toBe("Hoje");
    expect(rotuloDia("2026-10-19", "2026-10-18")).toBe("Amanhã");
    expect(rotuloDia("2026-10-24", "2026-10-18")).toBe("sábado, 24 de outubro");
    expect(rotuloDia("2027-01-02", "2026-12-31")).toBe("sábado, 2 de janeiro");
  });
});
