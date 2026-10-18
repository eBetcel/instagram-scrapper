import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { Cartao } from "@/components/ui/Cartao";
import { Carregando } from "@/components/ui/Carregando";
import { Titulo } from "@/components/ui/Titulo";
import { Vazio } from "@/components/ui/Vazio";
import { apiServidor } from "@/lib/api-servidor";
import type { Grupo } from "@/lib/tipos";
import { NovoGrupo } from "./NovoGrupo";

export const metadata: Metadata = { title: "Grupos" };

function Lista({ titulo, grupos, vazio }: { titulo: string; grupos: Grupo[]; vazio: string }) {
  return (
    <section className="space-y-2">
      <Titulo nivel={2}>{titulo}</Titulo>
      {grupos.length === 0 ? (
        <Vazio>{vazio}</Vazio>
      ) : (
        <Cartao as="ul" className="divide-y divide-linha">
          {grupos.map((g) => (
            <li key={g.slug} className="px-4 py-3">
              <Link href={`/g/${g.slug}`} className="font-medium text-tinta hover:underline">{g.nome}</Link>
              <p className="text-xs text-apagado">
                {g.n_perfis} @{g.n_perfis === 1 ? "" : "s"} · {g.n_seguidores} seguidor{g.n_seguidores === 1 ? "" : "es"}
              </p>
            </li>
          ))}
        </Cartao>
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
      <Titulo nivel={1}>Grupos</Titulo>
      <Suspense fallback={<Carregando />}>
        <MeusGrupos />
        <NovoGrupo />
      </Suspense>
    </section>
  );
}
