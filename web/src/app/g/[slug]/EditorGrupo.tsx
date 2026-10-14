"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Aviso } from "@/components/Aviso";
import { botao, botaoSecundario, campo } from "@/components/campos";
import { chamarApi } from "@/lib/api-cliente";
import { STATUS_PERFIL as STATUS } from "@/lib/formato";
import type { GrupoDetalhe } from "@/lib/tipos";

export function EditorGrupo({ grupo }: { grupo: GrupoDetalhe }) {
  const router = useRouter();
  const [nome, setNome] = useState(grupo.nome);
  const [descricao, setDescricao] = useState(grupo.descricao ?? "");
  const [username, setUsername] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const base = `/grupos/${grupo.slug}`;

  async function executar(acao: () => ReturnType<typeof chamarApi>, sucesso?: () => void) {
    setErro(null);
    setAviso(null);
    const r = await acao();
    if (!r.ok) return setErro(r.mensagem);
    sucesso?.();
    router.refresh();
  }

  return (
    <section className="space-y-5 rounded-lg border border-stone-200 bg-white p-4">
      <h2 className="font-semibold">Editar grupo</h2>
      {erro && <Aviso>{erro}</Aviso>}
      {aviso && <Aviso tipo="info">{aviso}</Aviso>}

      <form className="space-y-2" onSubmit={(e) => {
        e.preventDefault();
        executar(() => chamarApi(base, { method: "PATCH", body: JSON.stringify({ nome, descricao }) }),
          () => setAviso("Grupo salvo."));
      }}>
        <input aria-label="Nome do grupo" required maxLength={80} value={nome} onChange={(e) => setNome(e.target.value)} className={campo} />
        <textarea aria-label="Descrição do grupo" maxLength={500} value={descricao} onChange={(e) => setDescricao(e.target.value)} className={campo} rows={2} />
        <button type="submit" className={botaoSecundario}>Salvar</button>
      </form>

      <div className="space-y-2">
        <h3 className="text-sm font-semibold">Perfis do Instagram</h3>
        <ul className="space-y-1 text-sm">
          {grupo.perfis.map((p) => (
            <li key={p.username} className="flex items-center justify-between gap-2">
              <span>@{p.username}{STATUS[p.status] && <span className="text-stone-500"> · {STATUS[p.status]}</span>}</span>
              <button type="button" className="text-red-700 underline"
                onClick={() => executar(() => chamarApi(`${base}/perfis/${p.username}`, { method: "DELETE" }))}>
                remover
              </button>
            </li>
          ))}
        </ul>
        <form className="flex gap-2" onSubmit={(e) => {
          e.preventDefault();
          executar(() => chamarApi(`${base}/perfis`, { method: "POST", body: JSON.stringify({ username }) }),
            () => setUsername(""));
        }}>
          <input aria-label="Adicionar @" required value={username} onChange={(e) => setUsername(e.target.value)}
            placeholder="@perfil" className={campo} />
          <button type="submit" className={botao}>Adicionar</button>
        </form>
      </div>

      <div className="flex flex-wrap gap-2">
        <button type="button" className={botaoSecundario} onClick={async () => {
          await navigator.clipboard.writeText(location.href);
          setAviso("Link copiado. Quem abrir pode seguir o grupo.");
        }}>Copiar link</button>
        <button type="button" className="rounded-md px-3 py-2 text-sm text-red-700 underline" onClick={() => {
          if (!confirm(`Apagar o grupo "${grupo.nome}"? Quem segue deixa de ver os eventos dele.`)) return;
          executar(() => chamarApi(base, { method: "DELETE" }), () => router.push("/grupos"));
        }}>Apagar grupo</button>
      </div>
    </section>
  );
}
