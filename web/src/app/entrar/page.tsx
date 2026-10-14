import type { Metadata } from "next";
import { Suspense } from "react";
import { Aviso } from "@/components/Aviso";
import { FormularioEntrar } from "./FormularioEntrar";

export const metadata: Metadata = { title: "Entrar" };

async function AvisoDoLink({ searchParams }: { searchParams: PageProps<"/entrar">["searchParams"] }) {
  const { erro } = await searchParams;
  return erro === "link" ? <Aviso>Link inválido ou vencido. Peça outro.</Aviso> : null;
}

export default function Entrar({ searchParams }: PageProps<"/entrar">) {
  return (
    <section className="mx-auto max-w-sm space-y-4">
      <h1 className="text-xl font-semibold">Entrar</h1>
      <Suspense fallback={null}>
        <AvisoDoLink searchParams={searchParams} />
      </Suspense>
      <FormularioEntrar />
    </section>
  );
}
