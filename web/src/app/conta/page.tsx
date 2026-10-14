import type { Metadata } from "next";
import { Suspense } from "react";
import { Carregando } from "@/components/Carregando";
import { apiServidor } from "@/lib/api-servidor";
import type { Usuario } from "@/lib/tipos";
import { BotaoSair } from "./BotaoSair";

export const metadata: Metadata = { title: "Conta" };

async function DadosDaConta() {
  const eu = await apiServidor<Usuario>("/api/eu");
  return (
    <dl className="space-y-2 text-sm">
      <div><dt className="text-stone-500">Nome</dt><dd>{eu.nome}</dd></div>
      <div><dt className="text-stone-500">E-mail</dt><dd>{eu.email}</dd></div>
    </dl>
  );
}

export default function Conta() {
  return (
    <section className="space-y-6">
      <h1 className="text-xl font-semibold">Conta</h1>
      <Suspense fallback={<Carregando />}>
        <DadosDaConta />
        <BotaoSair />
      </Suspense>
    </section>
  );
}
