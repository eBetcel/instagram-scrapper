import Link from "next/link";
import { connection } from "next/server";
import { Suspense } from "react";
import { Carregando } from "@/components/Carregando";
import { ListaPorDia } from "@/components/ListaPorDia";
import { apiServidor } from "@/lib/api-servidor";
import { intervalo, PERIODOS, type Periodo } from "@/lib/datas";
import type { Evento, Grupo } from "@/lib/tipos";
import { Filtros, type ValoresFiltro } from "./Filtros";

type Busca = PageProps<"/">["searchParams"];

function texto(v: string | string[] | undefined): string {
  return typeof v === "string" ? v : "";
}

async function ConteudoDaAgenda({ searchParams }: { searchParams: Busca }) {
  await connection(); // o "hoje" muda a cada requisição
  const busca = await searchParams;
  const periodo = (PERIODOS as string[]).includes(texto(busca.periodo)) ? (texto(busca.periodo) as Periodo) : "semana";
  const valores: ValoresFiltro = {
    periodo, grupo: texto(busca.grupo), categoria: texto(busca.categoria), gratuito: texto(busca.gratuito) === "1",
  };
  const { de, ate } = intervalo(periodo, new Date());
  const q = new URLSearchParams({ de, ate });
  if (valores.grupo) q.set("grupo", valores.grupo);
  if (valores.categoria) q.set("categoria", valores.categoria);
  if (valores.gratuito) q.set("gratuito", "true");
  const [{ eventos }, { meus, seguidos }] = await Promise.all([
    apiServidor<{ eventos: Evento[] }>(`/api/agenda?${q}`),
    apiServidor<{ meus: Grupo[]; seguidos: Grupo[] }>("/api/grupos"),
  ]);
  const grupos = [...meus, ...seguidos];
  if (grupos.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-stone-300 p-4 text-sm">
        <Link href="/grupos" className="font-medium underline">Crie um grupo com os @s que você acompanha</Link>
        {" "}e os eventos deles aparecem aqui.
      </p>
    );
  }
  return (
    <div className="space-y-6">
      <Filtros valores={valores} grupos={grupos} />
      {eventos.length === 0 ? (
        <p className="text-sm text-stone-500">Nenhum evento neste período.</p>
      ) : (
        <ListaPorDia eventos={eventos} />
      )}
    </div>
  );
}

export default function Agenda({ searchParams }: PageProps<"/">) {
  return (
    <section className="space-y-4">
      <h1 className="text-xl font-semibold">Agenda</h1>
      <Suspense fallback={<Carregando />}>
        <ConteudoDaAgenda searchParams={searchParams} />
      </Suspense>
    </section>
  );
}
