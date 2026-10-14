import { FUSO } from "./datas";
import type { Evento } from "./tipos";

const horaMinuto = new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO, hour: "2-digit", minute: "2-digit" });
const inteiro = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const centavos = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** "R$ 40" para valor inteiro, "R$ 60,50" com centavos. */
function reais(valor: number): string {
  return `R$ ${(Number.isInteger(valor) ? inteiro : centavos).format(valor)}`;
}

export function hora(e: Evento): string {
  return e.hora_definida ? horaMinuto.format(new Date(e.inicio)) : "horário a confirmar";
}

export function preco(e: Evento): string | null {
  const min = e.preco_min === null ? null : Number(e.preco_min);
  const max = e.preco_max === null ? null : Number(e.preco_max);
  if (e.gratuito || max === 0) return "Grátis";
  if (min !== null && max !== null && min !== max) return `${reais(min)} a ${reais(max)}`;
  const unico = max ?? min;
  if (unico !== null) return reais(unico);
  return e.preco_texto;
}

const SELOS_STATUS: Partial<Record<Evento["status"], string>> = {
  cancelado: "❌ cancelado",
  esgotado: "🔴 esgotado",
  adiado: "⏸ adiado",
};

export function selos(e: Evento): string[] {
  const lista = e.alterado ? ["⚠️ alterado"] : [];
  const status = SELOS_STATUS[e.status];
  return status ? [...lista, status] : lista;
}

export const CATEGORIAS: Record<Evento["categoria"], string> = {
  show: "Show", festa: "Festa", exposicao: "Exposição", teatro: "Teatro",
  cinema: "Cinema", oficina: "Oficina", festival: "Festival", outro: "Outro",
};
