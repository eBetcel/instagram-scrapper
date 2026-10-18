// Datas sempre no fuso de São Paulo, independente do fuso do servidor ou do navegador.
// Dias são strings AAAA-MM-DD; a aritmética de dias é feita em UTC sobre essas datas.
import type { Evento } from "./tipos";

export const FUSO = "America/Sao_Paulo";
export type Periodo = "hoje" | "fim-de-semana" | "semana" | "mes" | "proximos";
export const PERIODOS: Periodo[] = ["hoje", "fim-de-semana", "semana", "mes", "proximos"];
const DIAS_PROXIMOS = 60;

const dataIso = new Intl.DateTimeFormat("en-CA", { timeZone: FUSO, year: "numeric", month: "2-digit", day: "2-digit" });

export function diaDe(momento: string | Date): string {
  return dataIso.format(typeof momento === "string" ? new Date(momento) : momento);
}

function comoUtc(dia: string): Date {
  const [a, m, d] = dia.split("-").map(Number);
  return new Date(Date.UTC(a, m - 1, d));
}

function somarDias(dia: string, n: number): string {
  const d = comoUtc(dia);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export function intervalo(periodo: Periodo, agora: Date): { de: string; ate: string } {
  const hoje = diaDe(agora);
  const semana = comoUtc(hoje).getUTCDay(); // 0 = domingo, 6 = sábado
  switch (periodo) {
    case "hoje":
      return { de: hoje, ate: hoje };
    case "fim-de-semana": {
      if (semana === 0) return { de: somarDias(hoje, -1), ate: hoje };
      const sabado = somarDias(hoje, 6 - semana);
      return { de: semana === 6 ? hoje : sabado, ate: somarDias(sabado, 1) };
    }
    case "semana":
      return { de: hoje, ate: somarDias(hoje, 6) };
    case "mes": {
      const d = comoUtc(hoje);
      const ultimo = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0));
      return { de: hoje, ate: ultimo.toISOString().slice(0, 10) };
    }
    case "proximos":
      return { de: hoje, ate: somarDias(hoje, DIAS_PROXIMOS) };
  }
}

export function agruparPorDia(eventos: Evento[]): { dia: string; eventos: Evento[] }[] {
  const grupos: { dia: string; eventos: Evento[] }[] = [];
  for (const e of eventos) {
    const dia = diaDe(e.inicio);
    const ultimo = grupos.at(-1);
    if (ultimo?.dia === dia) ultimo.eventos.push(e);
    else grupos.push({ dia, eventos: [e] });
  }
  return grupos;
}

const diaPorExtenso = new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC", weekday: "long", day: "numeric", month: "long" });

export function rotuloDia(dia: string, hoje: string): string {
  if (dia === hoje) return "Hoje";
  if (dia === somarDias(hoje, 1)) return "Amanhã";
  return diaPorExtenso.format(comoUtc(dia));
}
