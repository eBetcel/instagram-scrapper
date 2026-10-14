import Link from "next/link";
import { hora, preco, selos } from "@/lib/formato";
import type { Evento } from "@/lib/tipos";

export function EventoCard({ evento }: { evento: Evento }) {
  const valor = preco(evento);
  const onde = [evento.local_nome, evento.cidade].filter(Boolean).join(" · ");
  return (
    <article className="flex gap-3 rounded-lg border border-stone-200 bg-white p-3">
      {evento.imagem ? (
        // eslint-disable-next-line @next/next/no-img-element -- flyer servido pela api, já na mesma origem
        <img src={evento.imagem} alt="" loading="lazy" className="h-20 w-20 flex-none rounded-md object-cover" />
      ) : (
        <div aria-hidden className="h-20 w-20 flex-none rounded-md bg-stone-100" />
      )}
      <div className="min-w-0 flex-1 space-y-1">
        {selos(evento).length > 0 && (
          <p className="flex flex-wrap gap-1 text-xs">
            {selos(evento).map((s) => <span key={s} className="rounded bg-amber-50 px-1.5 py-0.5">{s}</span>)}
          </p>
        )}
        <h3 className="font-medium leading-snug">
          <Link href={`/evento/${evento.id}`} className="hover:underline">{evento.titulo}</Link>
        </h3>
        <p className="text-sm text-stone-600">{hora(evento)}{onde && ` · ${onde}`}</p>
        <p className="flex flex-wrap items-center gap-3 text-sm">
          {valor && <span>{valor}</span>}
          {evento.link_ingresso && (
            <a href={evento.link_ingresso} target="_blank" rel="noopener noreferrer" className="text-blue-700 underline">Ingressos</a>
          )}
        </p>
      </div>
    </article>
  );
}
