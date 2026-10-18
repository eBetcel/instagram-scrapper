import type { Metadata } from "next";
import { Suspense } from "react";
import { Carregando } from "@/components/ui/Carregando";
import { Cartao } from "@/components/ui/Cartao";
import { Titulo } from "@/components/ui/Titulo";
import { apiServidor } from "@/lib/api-servidor";
import type { Usuario } from "@/lib/tipos";
import { BotaoSair } from "./BotaoSair";

export const metadata: Metadata = { title: "Conta" };

async function DadosDaConta() {
  const eu = await apiServidor<Usuario>("/api/eu");
  return (
    <Cartao className="space-y-3 p-4 text-sm"><dl className="space-y-3">
      <div><dt className="text-apagado">Nome</dt><dd className="text-tinta">{eu.nome}</dd></div>
      <div><dt className="text-apagado">E-mail</dt><dd className="text-tinta">{eu.email}</dd></div>
    </dl></Cartao>
  );
}

export default function Conta() {
  return (
    <section className="space-y-6">
      <Titulo nivel={1}>Conta</Titulo>
      <Suspense fallback={<Carregando />}>
        <DadosDaConta />
        <BotaoSair />
      </Suspense>
    </section>
  );
}
