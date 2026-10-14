// Chamadas à api feitas no navegador (Client Components), sempre na mesma origem.

export type RespostaApi<T> =
  | { ok: true; dados: T }
  | { ok: false; status: number; mensagem: string; corpo: unknown };

const GENERICA = "Algo deu errado. Tente de novo.";
const VALIDACAO = "Confira os dados informados.";

export async function chamarApi<T = unknown>(caminho: string, init?: RequestInit): Promise<RespostaApi<T>> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("content-type")) headers.set("content-type", "application/json");
  let r: Response;
  try {
    r = await fetch(`/api${caminho}`, { ...init, headers, credentials: "same-origin" });
  } catch {
    return { ok: false, status: 0, mensagem: GENERICA, corpo: null };
  }
  let corpo: unknown = null;
  try {
    corpo = r.status === 204 ? null : await r.json();
  } catch {}
  if (r.ok) return { ok: true, dados: corpo as T };
  const detail = (corpo as { detail?: unknown } | null)?.detail;
  const mensagem = typeof detail === "string" ? detail : Array.isArray(detail) ? VALIDACAO : GENERICA;
  return { ok: false, status: r.status, mensagem, corpo };
}
