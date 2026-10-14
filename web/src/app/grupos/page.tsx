import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { Carregando } from "@/components/Carregando";
import { apiServidor } from "@/lib/api-servidor";
import type { Grupo } from "@/lib/tipos";
import { NovoGrupo } from "./NovoGrupo";

export const metadata: Metadata = { title: "Grupos" };

function Lista({ titulo, grupos, vazio }: { titulo: string; grupos: Grupo[]; vazio: string }) {
  return (
    <section className="space-y-2">
      <h2 className="font-semibold">{titulo}</h2>
      {grupos.length === 0 ? (
        <p className="text-sm text-stone-500">{vazio}</p>
      ) : (
        <ul className="divide-y divide-stone-200 rounded-lg border border-stone-200 bg-white">
          {grupos.map((g) => (
            <li key={g.slug} className="px-3 py-2">
              <Link href={`/g/${g.slug}`} className="font-medium hover:underline">{g.nome}</Link>
              <p className="text-xs text-stone-500">
                {g.n_perfis} @{g.n_perfis === 1 ? "" : "s"} · {g.n_seguidores} seguidor{g.n_seguidores === 1 ? "" : "es"}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

async function MeusGrupos() {
  const { meus, seguidos } = await apiServidor<{ meus: Grupo[]; seguidos: Grupo[] }>("/api/grupos");
  return (
    <div className="space-y-6">
      <Lista titulo="Meus grupos" grupos={meus} vazio="Você ainda não criou nenhum grupo." />
      <Lista titulo="Grupos que sigo" grupos={seguidos} vazio="Quando alguém compartilhar um grupo com você, siga-o pela página dele." />
    </div>
  );
}

export default function Grupos() {
  return (
    <section className="space-y-6">
      <h1 className="text-xl font-semibold">Grupos</h1>
      <Suspense fallback={<Carregando />}>
        <MeusGrupos />
        <NovoGrupo />
      </Suspense>
    </section>
  );
}
