import { agruparPorDia, diaDe, rotuloDia } from "@/lib/datas";
import type { Evento } from "@/lib/tipos";
import { EventoCard } from "./EventoCard";

export function ListaPorDia({ eventos }: { eventos: Evento[] }) {
  const hoje = diaDe(new Date());
  return (
    <div className="space-y-6">
      {agruparPorDia(eventos).map(({ dia, eventos }) => (
        <section key={dia} className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-stone-500">{rotuloDia(dia, hoje)}</h2>
          {eventos.map((e) => <EventoCard key={e.id} evento={e} />)}
        </section>
      ))}
    </div>
  );
}
