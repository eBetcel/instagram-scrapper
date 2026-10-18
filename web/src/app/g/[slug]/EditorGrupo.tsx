"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Aviso } from "@/components/Aviso";
import { botao, botaoSecundario, campo } from "@/components/campos";
import { chamarApi } from "@/lib/api-cliente";
import { STATUS_PERFIL as STATUS } from "@/lib/formato";
import { adicionarPendente, restantes } from "@/lib/pendentes";
import type { GrupoDetalhe, ResultadoPerfil } from "@/lib/tipos";

export function EditorGrupo({ grupo }: { grupo: GrupoDetalhe }) {
  const router = useRouter();
  const [nome, setNome] = useState(grupo.nome);
  const [descricao, setDescricao] = useState(grupo.descricao ?? "");
  const [username, setUsername] = useState("");
  const [pendentes, setPendentes] = useState<string[]>([]);
  const [recusados, setRecusados] = useState<Record<string, string>>({});
  const [confirmando, setConfirmando] = useState(false);
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

  async function confirmar() {
    setErro(null);
    setAviso(null);
    setConfirmando(true);
    const r = await chamarApi<{ resultados: ResultadoPerfil[] }>(`${base}/perfis/lote`, {
      method: "POST", body: JSON.stringify({ usernames: pendentes }),
    });
    setConfirmando(false);
    if (!r.ok) return setErro(r.mensagem);
    const sobras = restantes(pendentes, r.dados.resultados);
    const aceitos = pendentes.length - sobras.length;
    setPendentes(sobras.map((x) => x.username));
    setRecusados(Object.fromEntries(sobras.map((x) => [x.username, x.erro])));
    if (aceitos) setAviso(`${aceitos} perfil(is) adicionado(s). Os novos estão sendo coletados e logo aparecem na agenda.`);
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
          setPendentes((lista) => adicionarPendente(lista, username));
          setUsername("");
        }}>
          <input aria-label="Adicionar @" required value={username} onChange={(e) => setUsername(e.target.value)}
            placeholder="@perfil" className={campo} />
          <button type="submit" className={botaoSecundario}>Adicionar</button>
        </form>
        {pendentes.length > 0 && (
          <div className="space-y-2 rounded-md bg-stone-50 p-3">
            <p className="text-sm font-medium">Para confirmar</p>
            <ul className="space-y-1 text-sm">
              {pendentes.map((p) => (
                <li key={p} className="flex items-center justify-between gap-2">
                  <span>@{p}{recusados[p] && <span className="text-red-700"> · {recusados[p]}</span>}</span>
                  <button type="button" className="text-stone-600 underline"
                    onClick={() => setPendentes((lista) => lista.filter((x) => x !== p))}>
                    descartar
                  </button>
                </li>
              ))}
            </ul>
            <button type="button" className={botao} disabled={confirmando} onClick={confirmar}>
              {confirmando ? "Confirmando…" : `Confirmar (${pendentes.length})`}
            </button>
          </div>
        )}
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
