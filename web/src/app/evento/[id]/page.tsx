import type { Metadata } from "next";
import { Suspense } from "react";
import { Botao } from "@/components/ui/Botao";
import { Cartao } from "@/components/ui/Cartao";
import { Carregando } from "@/components/ui/Carregando";
import { Selo } from "@/components/ui/Selo";
import { Titulo } from "@/components/ui/Titulo";
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
        <img src={e.imagem} alt={`Flyer de ${e.titulo}`} className="w-full rounded-xl object-contain" />
      )}
      <header className="space-y-1">
        {selos(e).length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {selos(e).map((s) => <Selo key={s} tom="acento">{s}</Selo>)}
          </div>
        )}
        <Titulo nivel={1} className="break-words">{e.titulo}</Titulo>
        <p className="text-texto">{rotuloDia(diaDe(e.inicio), diaDe(new Date()))} · {hora(e)}</p>
      </header>
      <Cartao className="p-4 text-sm">
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
        {e.local_nome && <><dt className="text-apagado">Local</dt><dd className="break-words text-tinta">{e.local_nome}</dd></>}
        {e.endereco && <><dt className="text-apagado">Endereço</dt><dd className="break-words text-tinta">{e.endereco}</dd></>}
        {e.cidade && <><dt className="text-apagado">Cidade</dt><dd className="break-words text-tinta">{e.cidade}</dd></>}
        {valor && <><dt className="text-apagado">Preço</dt><dd className="break-words text-tinta">{valor}</dd></>}
        {e.festival && <><dt className="text-apagado">Festival</dt><dd className="break-words text-tinta">{e.festival}</dd></>}
      </dl>
      </Cartao>
      {e.link_ingresso && (
        <Botao variante="primario" href={e.link_ingresso} externo className="w-full md:w-auto">Ingressos</Botao>
      )}
      {e.artistas.length > 0 && (
        <section className="space-y-1">
          <Titulo nivel={2}>Artistas</Titulo>
          <p className="text-sm text-texto">{e.artistas.join(", ")}</p>
        </section>
      )}
      {e.descricao && <p className="whitespace-pre-line text-sm text-texto">{e.descricao}</p>}
      <section className="space-y-1">
        <Titulo nivel={2}>Divulgado por</Titulo>
        <ul className="space-y-1 text-sm">
          {e.fontes.map((f) => (
            <li key={f.shortcode}>
              <a href={f.url_instagram} target="_blank" rel="noopener noreferrer" className="text-acento-forte underline underline-offset-2">{`@${f.username}`}</a>
              {f.publicado_em && <span className="text-apagado"> · {data.format(new Date(f.publicado_em))}</span>}
            </li>
          ))}
        </ul>
      </section>
      {e.revisoes.length > 0 && (
        <section className="space-y-1">
          <Titulo nivel={2}>Histórico</Titulo>
          <ul className="space-y-1 text-sm">
            {e.revisoes.map((r, i) => (
              <li key={i}>
                <span className="text-apagado">{data.format(new Date(r.criado_em))}</span>{" "}
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
