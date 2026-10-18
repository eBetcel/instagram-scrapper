import type { Metadata } from "next";
import { Suspense } from "react";
import { Aviso } from "@/components/ui/Aviso";
import { Cartao } from "@/components/ui/Cartao";
import { Titulo } from "@/components/ui/Titulo";
import { FormularioEntrar } from "./FormularioEntrar";

export const metadata: Metadata = { title: "Entrar" };

async function AvisoDoLink({ searchParams }: { searchParams: PageProps<"/entrar">["searchParams"] }) {
  const { erro } = await searchParams;
  return erro === "link" ? <Aviso>Link inválido ou vencido. Peça outro.</Aviso> : null;
}

export default function Entrar({ searchParams }: PageProps<"/entrar">) {
  return (
    <section className="mx-auto max-w-sm space-y-4 pt-4 md:pt-10">
      <Titulo nivel={1}>Entrar</Titulo>
      <Suspense fallback={null}>
        <AvisoDoLink searchParams={searchParams} />
      </Suspense>
      <Cartao className="p-6">
        <FormularioEntrar />
      </Cartao>
    </section>
  );
}
