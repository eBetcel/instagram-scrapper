export const foco =
  "focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-acento/25";

export type VarianteBotao = "primario" | "secundario" | "fantasma" | "perigo";
export type TamanhoBotao = "md" | "sm";

const baseBotao =
  "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium disabled:opacity-50 disabled:cursor-default";

const tamanhos: Record<TamanhoBotao, string> = {
  md: "min-h-11 px-4 text-sm",
  sm: "min-h-9 px-3 text-sm",
};

const variantes: Record<VarianteBotao, string> = {
  primario: "bg-acento text-sobre-acento active:bg-acento-forte",
  secundario: "border border-linha bg-superficie text-tinta active:bg-suave",
  fantasma: "text-acento-forte active:bg-suave",
  perigo: "text-erro active:bg-erro/10",
};

export function classesBotao(
  variante: VarianteBotao = "secundario",
  tamanho: TamanhoBotao = "md",
): string {
  return `${baseBotao} ${tamanhos[tamanho]} ${variantes[variante]} ${foco}`;
}

export function classesChip(ativo: boolean): string {
  const base =
    "min-h-9 px-3.5 rounded-full border text-sm font-medium whitespace-nowrap";
  const estado = ativo
    ? "border-tinta bg-tinta text-fundo"
    : "border-linha bg-superficie text-texto";
  return `${base} ${estado} ${foco}`;
}

export type TomSelo = "neutro" | "acento";

export function classesSelo(tom: TomSelo = "neutro"): string {
  const base = "rounded-full px-2.5 py-0.5 text-xs font-medium";
  return `${base} ${tom === "acento" ? "bg-acento/12 text-acento-forte" : "bg-suave text-texto"}`;
}

export type TipoAviso = "erro" | "info" | "sucesso";

const avisos: Record<TipoAviso, string> = {
  erro: "bg-erro/8 border-erro/25 text-erro",
  info: "bg-sucesso/8 border-sucesso/25 text-sucesso",
  sucesso: "bg-sucesso/8 border-sucesso/25 text-sucesso",
};

export function classesAviso(tipo: TipoAviso = "erro"): string {
  return `rounded-lg border px-3 py-2 text-sm ${avisos[tipo]}`;
}
