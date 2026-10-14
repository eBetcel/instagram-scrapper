"use client";

import { useRouter } from "next/navigation";
import { chamarApi } from "@/lib/api-cliente";

export function BotaoSair() {
  const router = useRouter();
  async function sair() {
    await chamarApi("/auth/sair", { method: "POST" });
    router.push("/entrar");
    router.refresh();
  }
  return (
    <button onClick={sair} className="rounded-md border border-stone-300 px-3 py-2 text-sm">
      Sair
    </button>
  );
}
