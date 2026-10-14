"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { botao, botaoSecundario } from "@/components/campos";
import { chamarApi } from "@/lib/api-cliente";

export function BotaoSeguir({ slug, logado, sigo }: { slug: string; logado: boolean; sigo: boolean }) {
  const router = useRouter();
  const [enviando, setEnviando] = useState(false);
  if (!logado) return <Link href="/entrar" className={`inline-block ${botao}`}>Seguir</Link>;
  async function alternar() {
    setEnviando(true);
    await chamarApi(`/grupos/${slug}/seguir`, { method: sigo ? "DELETE" : "POST" });
    setEnviando(false);
    router.refresh();
  }
  return (
    <button onClick={alternar} disabled={enviando} className={sigo ? botaoSecundario : botao}>
      {sigo ? "Deixar de seguir" : "Seguir"}
    </button>
  );
}
