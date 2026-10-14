import type { Metadata } from "next";
import { Suspense } from "react";
import { Carregando } from "@/components/Carregando";
import { apiServidor } from "@/lib/api-servidor";
import { diaDe, FUSO, rotuloDia } from "@/lib/datas";
import { hora, preco, selos } from "@/lib/formato";
import type { EventoDetalhe } from "@/lib/tipos";

export const metadata: Metadata = { title: "Evento" };

const CAMPOS: Record<string, string> = {
  titulo: "Título", descricao: "Descrição", inicio: "Data e hora", fim: "Fim", local_nome: "Local",
  endereco: "Endereço", cidade: "Cidade", categoria: "Categoria", preco_texto: "Preço",
  gratuito: "Gratuito", preco_min: "Preço mínimo", preco_max: "Preço máximo",
  link_ingresso: "Ingressos", artistas: "Artistas", festival: "Festival", status: "Situação",
};

const dataHora = new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO, dateStyle: "short", timeStyle: "short" });
const data = new Intl.DateTimeFormat("pt-BR", { timeZone: FUSO, dateStyle: "short" });

function valorRevisao(campo: string, valor: string | null): string {
  if (valor === null || valor === "") return "—";
  if (campo === "inicio" || campo === "fim") return dataHora.format(new Date(valor));
  return valor;
}

async function Detalhe({ params }: { params: PageProps<"/evento/[id]">["params"] }) {
  const { id } = await params;
  const e = await apiServidor<EventoDetalhe>(`/api/eventos/${encodeURIComponent(id)}`);
  const valor = preco(e);
  return (
    <article className="space-y-5">
      {e.imagem && (
        // eslint-disable-next-line @next/next/no-img-element -- flyer servido pela api, já na mesma origem
        <img src={e.imagem} alt={`Flyer de ${e.titulo}`} className="w-full rounded-lg object-contain" />
      )}
      <header className="space-y-1">
        {selos(e).length > 0 && <p className="text-sm">{selos(e).join("  ")}</p>}
        <h1 className="text-2xl font-semibold">{e.titulo}</h1>
        <p className="text-stone-700">{rotuloDia(diaDe(e.inicio), diaDe(new Date()))} · {hora(e)}</p>
      </header>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        {e.local_nome && <><dt className="text-stone-500">Local</dt><dd>{e.local_nome}</dd></>}
        {e.endereco && <><dt className="text-stone-500">Endereço</dt><dd>{e.endereco}</dd></>}
        {e.cidade && <><dt className="text-stone-500">Cidade</dt><dd>{e.cidade}</dd></>}
        {valor && <><dt className="text-stone-500">Preço</dt><dd>{valor}</dd></>}
        {e.festival && <><dt className="text-stone-500">Festival</dt><dd>{e.festival}</dd></>}
      </dl>
      {e.link_ingresso && (
        <a href={e.link_ingresso} target="_blank" rel="noopener noreferrer"
          className="inline-block rounded-md bg-stone-900 px-4 py-2 text-sm font-medium text-white">Ingressos</a>
      )}
      {e.artistas.length > 0 && (
        <section className="space-y-1">
          <h2 className="font-semibold">Artistas</h2>
          <p className="text-sm">{e.artistas.join(", ")}</p>
        </section>
      )}
      {e.descricao && <p className="whitespace-pre-line text-sm">{e.descricao}</p>}
      <section className="space-y-1">
        <h2 className="font-semibold">Divulgado por</h2>
        <ul className="space-y-1 text-sm">
          {e.fontes.map((f) => (
            <li key={f.shortcode}>
              <a href={f.url_instagram} target="_blank" rel="noopener noreferrer" className="text-blue-700 underline">{`@${f.username}`}</a>
              {f.publicado_em && <span className="text-stone-500"> · {data.format(new Date(f.publicado_em))}</span>}
            </li>
          ))}
        </ul>
      </section>
      {e.revisoes.length > 0 && (
        <section className="space-y-1">
          <h2 className="font-semibold">Histórico</h2>
          <ul className="space-y-1 text-sm">
            {e.revisoes.map((r, i) => (
              <li key={i}>
                <span className="text-stone-500">{data.format(new Date(r.criado_em))}</span>{" "}
                {CAMPOS[r.campo] ?? r.campo}: {valorRevisao(r.campo, r.valor_anterior)} → {valorRevisao(r.campo, r.valor_novo)}
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}

export default function Evento({ params }: PageProps<"/evento/[id]">) {
  return (
    <Suspense fallback={<Carregando />}>
      <Detalhe params={params} />
    </Suspense>
  );
}
