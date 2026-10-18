"use client";

import { useRouter } from "next/navigation";
import { Chip } from "@/components/ui/Chip";
import { Seletor } from "@/components/ui/Seletor";
import type { Periodo } from "@/lib/datas";
import { CATEGORIAS } from "@/lib/formato";
import type { Grupo } from "@/lib/tipos";

export type ValoresFiltro = { periodo: Periodo; grupo: string; categoria: string; gratuito: boolean };

const ROTULOS: Record<Periodo, string> = {
  hoje: "Hoje", "fim-de-semana": "Fim de semana", semana: "Semana", mes: "Mês",
};

export function Filtros({ valores, grupos }: { valores: ValoresFiltro; grupos: Grupo[] }) {
  const router = useRouter();
  function mudar(novo: Partial<ValoresFiltro>) {
    const v = { ...valores, ...novo };
    const q = new URLSearchParams({ periodo: v.periodo });
    if (v.grupo) q.set("grupo", v.grupo);
    if (v.categoria) q.set("categoria", v.categoria);
    if (v.gratuito) q.set("gratuito", "1");
    router.replace(`/?${q}`);
  }
  return (
    <div className="space-y-3">
      <div role="group" aria-label="Período" className="flex flex-wrap gap-2">
        {(Object.keys(ROTULOS) as Periodo[]).map((p) => (
          <Chip key={p} ativo={valores.periodo === p} onClick={() => mudar({ periodo: p })}>{ROTULOS[p]}</Chip>
        ))}
      </div>
      <div role="group" aria-label="Categoria" className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none]">
        <Chip ativo={valores.categoria === ""} onClick={() => mudar({ categoria: "" })}>Todas</Chip>
        {Object.entries(CATEGORIAS).map(([v, r]) => (
          <Chip key={v} ativo={valores.categoria === v} onClick={() => mudar({ categoria: valores.categoria === v ? "" : v })}>{r}</Chip>
        ))}
        <Chip ativo={valores.gratuito} onClick={() => mudar({ gratuito: !valores.gratuito })}>Grátis</Chip>
      </div>
      <Seletor aria-label="Grupo" value={valores.grupo} onChange={(e) => mudar({ grupo: e.target.value })} className="md:w-auto">
        <option value="">Todos os grupos</option>
        {grupos.map((g) => <option key={g.slug} value={g.slug}>{g.nome}</option>)}
      </Seletor>
    </div>
  );
}
