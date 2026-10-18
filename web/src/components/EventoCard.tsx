import Link from "next/link";
import { Botao } from "@/components/ui/Botao";
import { Cartao } from "@/components/ui/Cartao";
import { Selo } from "@/components/ui/Selo";
import { hora, preco, selos } from "@/lib/formato";
import type { Evento } from "@/lib/tipos";

export function EventoCard({ evento }: { evento: Evento }) {
  const valor = preco(evento);
  const onde = [evento.local_nome, evento.cidade].filter(Boolean).join(" · ");
  const alertas = selos(evento);
  return (
    <Cartao as="article" className="relative flex gap-3 p-3">
      {evento.imagem ? (
        // eslint-disable-next-line @next/next/no-img-element -- flyer servido pela api, já na mesma origem
        <img src={evento.imagem} alt="" loading="lazy" className="h-20 w-20 flex-none rounded-lg object-cover" />
      ) : (
        <div aria-hidden className="h-20 w-20 flex-none rounded-lg bg-suave" />
      )}
      <div className="min-w-0 flex-1 space-y-1">
        {alertas.length > 0 && (
          <p className="flex flex-wrap gap-1">
            {alertas.map((s) => <Selo key={s} tom="acento">{s}</Selo>)}
          </p>
        )}
        <p className="text-[13px] font-medium text-apagado">
          <span className="text-tinta">{hora(evento)}</span>{onde && ` · ${onde}`}
        </p>
        <h3 className="break-words text-base font-semibold leading-snug text-tinta">
          <Link href={`/evento/${evento.id}`} className="after:absolute after:inset-0 after:content-['']">{evento.titulo}</Link>
        </h3>
        <p className="relative z-10 flex flex-wrap items-center gap-3 text-sm">
          {valor && (valor === "Grátis" ? <Selo tom="acento">{valor}</Selo> : <span className="text-texto">{valor}</span>)}
          {evento.link_ingresso && (
            <Botao variante="fantasma" tamanho="sm" href={evento.link_ingresso} externo className="px-0">Ingressos →</Botao>
          )}
        </p>
      </div>
    </Cartao>
  );
}
