"use client";

import { useRouter } from "next/navigation";
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
  const caixa = "rounded-md border border-stone-300 bg-white px-2 py-1 text-sm";
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Período">
        {(Object.keys(ROTULOS) as Periodo[]).map((p) => (
          <button key={p} onClick={() => mudar({ periodo: p })} aria-pressed={valores.periodo === p}
            className={`rounded-full border px-3 py-1 text-sm ${valores.periodo === p ? "border-stone-900 bg-stone-900 text-white" : "border-stone-300 bg-white"}`}>
            {ROTULOS[p]}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <select aria-label="Grupo" value={valores.grupo} onChange={(e) => mudar({ grupo: e.target.value })} className={caixa}>
          <option value="">Todos os grupos</option>
          {grupos.map((g) => <option key={g.slug} value={g.slug}>{g.nome}</option>)}
        </select>
        <select aria-label="Categoria" value={valores.categoria} onChange={(e) => mudar({ categoria: e.target.value })} className={caixa}>
          <option value="">Todas as categorias</option>
          {Object.entries(CATEGORIAS).map(([v, r]) => <option key={v} value={v}>{r}</option>)}
        </select>
        <label className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={valores.gratuito} onChange={(e) => mudar({ gratuito: e.target.checked })} />
          Só gratuitos
        </label>
      </div>
    </div>
  );
}
