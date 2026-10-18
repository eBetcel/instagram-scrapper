// @s digitados no editor do grupo que ainda não foram confirmados.

import type { ResultadoPerfil } from "./tipos";

export function adicionarPendente(lista: string[], bruto: string): string[] {
  const username = bruto.trim().replace(/^@+/, "").toLowerCase();
  if (!username || lista.includes(username)) return lista;
  return [...lista, username];
}

/** O que a api recusou no lote, para o usuário corrigir ou descartar. */
export function restantes(pendentes: string[], resultados: ResultadoPerfil[]): { username: string; erro: string }[] {
  return pendentes.flatMap((username, i) => {
    const erro = resultados[i]?.erro;
    return erro ? [{ username, erro }] : [];
  });
}
