"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Aviso } from "@/components/Aviso";
import { botao, campo } from "@/components/campos";
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
    <form onSubmit={criar} className="space-y-3 rounded-lg border border-stone-200 bg-white p-4">
      <h2 className="font-semibold">Novo grupo</h2>
      <label className="block space-y-1 text-sm">
        <span>Nome</span>
        <input required maxLength={80} value={nome} onChange={(e) => setNome(e.target.value)}
          placeholder="Ex.: Jazz em Natal" className={campo} />
      </label>
      <label className="block space-y-1 text-sm">
        <span>Descrição (opcional)</span>
        <textarea maxLength={500} value={descricao} onChange={(e) => setDescricao(e.target.value)} className={campo} rows={2} />
      </label>
      {erro && <Aviso>{erro}</Aviso>}
      <button type="submit" disabled={enviando} className={botao}>{enviando ? "Criando…" : "Criar grupo"}</button>
    </form>
  );
}
