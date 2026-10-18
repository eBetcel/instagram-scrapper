"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { AreaTexto, Campo } from "@/components/ui/Campo";
import { Cartao } from "@/components/ui/Cartao";
import { Titulo } from "@/components/ui/Titulo";
import { chamarApi } from "@/lib/api-cliente";
import type { Grupo } from "@/lib/tipos";

export function NovoGrupo() {
  const router = useRouter();
  const [nome, setNome] = useState("");
  const [descricao, setDescricao] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function criar(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    setEnviando(true);
    const r = await chamarApi<Grupo>("/grupos", {
      method: "POST", body: JSON.stringify({ nome, descricao: descricao || null }),
    });
    setEnviando(false);
    if (!r.ok) return setErro(r.mensagem);
    router.push(`/g/${r.dados.slug}`);
  }

  return (
    <Cartao as="form" onSubmit={criar} className="space-y-3 p-4">
      <Titulo nivel={2}>Novo grupo</Titulo>
      <Campo rotulo="Nome" required maxLength={80} value={nome} onChange={(e) => setNome(e.target.value)}
        placeholder="Ex.: Jazz em Natal" />
      <AreaTexto rotulo="Descrição (opcional)" maxLength={500} value={descricao} onChange={(e) => setDescricao(e.target.value)} rows={2} />
      {erro && <Aviso>{erro}</Aviso>}
      <Botao variante="primario" type="submit" disabled={enviando}>{enviando ? "Criando…" : "Criar grupo"}</Botao>
    </Cartao>
  );
}
