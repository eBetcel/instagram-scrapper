"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { AreaTexto, Campo } from "@/components/ui/Campo";
import { Cartao } from "@/components/ui/Cartao";
import { Titulo } from "@/components/ui/Titulo";
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
    <Cartao as="section" className="space-y-5 p-4">
      <Titulo nivel={2}>Editar grupo</Titulo>
      {erro && <Aviso>{erro}</Aviso>}
      {aviso && <Aviso tipo="info">{aviso}</Aviso>}

      <form className="space-y-2" onSubmit={(e) => {
        e.preventDefault();
        executar(() => chamarApi(base, { method: "PATCH", body: JSON.stringify({ nome, descricao }) }),
          () => setAviso("Grupo salvo."));
      }}>
        <Campo aria-label="Nome do grupo" required maxLength={80} value={nome} onChange={(e) => setNome(e.target.value)} />
        <AreaTexto aria-label="Descrição do grupo" maxLength={500} value={descricao} onChange={(e) => setDescricao(e.target.value)} rows={2} />
        <Botao variante="secundario" type="submit">Salvar</Botao>
      </form>

      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-tinta">Perfis do Instagram</h3>
        <ul className="space-y-1 text-sm">
          {grupo.perfis.map((p) => (
            <li key={p.username} className="flex items-center justify-between gap-2">
              <span>@{p.username}{STATUS[p.status] && <span className="text-apagado"> · {STATUS[p.status]}</span>}</span>
              <Botao variante="perigo" tamanho="sm"
                onClick={() => executar(() => chamarApi(`${base}/perfis/${p.username}`, { method: "DELETE" }))}>
                remover
              </Botao>
            </li>
          ))}
        </ul>
        <form className="flex items-start gap-2" onSubmit={(e) => {
          e.preventDefault();
          setPendentes((lista) => adicionarPendente(lista, username));
          setUsername("");
        }}>
          <div className="min-w-0 flex-1">
            <Campo aria-label="Adicionar @" required value={username} onChange={(e) => setUsername(e.target.value)}
              placeholder="@perfil" />
          </div>
          <Botao variante="secundario" type="submit">Adicionar</Botao>
        </form>
        {pendentes.length > 0 && (
          <div className="space-y-2 rounded-lg bg-suave p-3">
            <p className="text-sm font-medium text-tinta">Para confirmar</p>
            <ul className="space-y-1 text-sm">
              {pendentes.map((p) => (
                <li key={p} className="flex items-center justify-between gap-2">
                  <span>@{p}{recusados[p] && <span className="text-erro"> · {recusados[p]}</span>}</span>
                  <Botao variante="fantasma" tamanho="sm"
                    onClick={() => setPendentes((lista) => lista.filter((x) => x !== p))}>
                    descartar
                  </Botao>
                </li>
              ))}
            </ul>
            <Botao variante="primario" disabled={confirmando} onClick={confirmar}>
              {confirmando ? "Confirmando…" : `Confirmar (${pendentes.length})`}
            </Botao>
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        <Botao variante="secundario" onClick={async () => {
          await navigator.clipboard.writeText(location.href);
          setAviso("Link copiado. Quem abrir pode seguir o grupo.");
        }}>Copiar link</Botao>
        <Botao variante="perigo" onClick={() => {
          if (!confirm(`Apagar o grupo "${grupo.nome}"? Quem segue deixa de ver os eventos dele.`)) return;
          executar(() => chamarApi(base, { method: "DELETE" }), () => router.push("/grupos"));
        }}>Apagar grupo</Botao>
      </div>
    </Cartao>
  );
}
