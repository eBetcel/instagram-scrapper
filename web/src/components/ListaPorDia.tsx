import { agruparPorDia, diaDe, rotuloDia } from "@/lib/datas";
import type { Evento } from "@/lib/tipos";
import { EventoCard } from "./EventoCard";

export function ListaPorDia({ eventos }: { eventos: Evento[] }) {
  const hoje = diaDe(new Date());
  return (
    <div className="space-y-6">
      {agruparPorDia(eventos).map(({ dia, eventos }) => (
        <section key={dia} className="space-y-2">
          <h2 className="sticky top-14 z-10 bg-fundo py-2 text-xs font-semibold uppercase tracking-[0.08em] text-apagado">{rotuloDia(dia, hoje)}</h2>
          {eventos.map((e) => <EventoCard key={e.id} evento={e} />)}
        </section>
      ))}
    </div>
  );
}
