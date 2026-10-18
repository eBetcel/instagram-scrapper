"use client";

import { useRouter } from "next/navigation";
import { Botao } from "@/components/ui/Botao";
import { chamarApi } from "@/lib/api-cliente";

export function BotaoSair() {
  const router = useRouter();
  async function sair() {
    await chamarApi("/auth/sair", { method: "POST" });
    router.push("/entrar");
    router.refresh();
  }
  return (
    <Botao onClick={sair}>Sair</Botao>
  );
}
