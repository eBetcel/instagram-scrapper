"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Botao } from "@/components/ui/Botao";
import { chamarApi } from "@/lib/api-cliente";

export function BotaoSeguir({ slug, logado, sigo }: { slug: string; logado: boolean; sigo: boolean }) {
  const router = useRouter();
  const [enviando, setEnviando] = useState(false);
  if (!logado) return <Botao variante="primario" href="/entrar">Seguir</Botao>;
  async function alternar() {
    setEnviando(true);
    await chamarApi(`/grupos/${slug}/seguir`, { method: sigo ? "DELETE" : "POST" });
    setEnviando(false);
    router.refresh();
  }
  return (
    <Botao variante={sigo ? "secundario" : "primario"} onClick={alternar} disabled={enviando}>
      {sigo ? "Deixar de seguir" : "Seguir"}
    </Botao>
  );
}
