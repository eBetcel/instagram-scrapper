// Chamadas à api feitas no servidor do Next (Server Components), com o cookie da pessoa.
// Com Cache Components, quem chama precisa estar dentro de um <Suspense>.
import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";

const COOKIE_SESSAO = "sessao";

async function chamar(caminho: string, init?: RequestInit): Promise<Response> {
  const base = process.env.API_URL_INTERNA ?? "http://localhost:8010";
  const sessao = (await cookies()).get(COOKIE_SESSAO)?.value;
  const headers = new Headers(init?.headers);
  if (sessao) headers.set("cookie", `${COOKIE_SESSAO}=${sessao}`);
  return fetch(`${base}${caminho}`, { ...init, headers, cache: "no-store" });
}

async function lerErro(r: Response): Promise<string> {
  try {
    const corpo = await r.json();
    if (typeof corpo?.detail === "string") return corpo.detail;
  } catch {}
  return `Erro ${r.status} da api`;
}

/** 401 leva a /entrar e 404 a notFound(); outros erros lançam com a mensagem da api. */
export async function apiServidor<T>(caminho: string, init?: RequestInit): Promise<T> {
  const r = await chamar(caminho, init);
  if (r.status === 401) redirect("/entrar");
  if (r.status === 404) notFound();
  if (!r.ok) throw new Error(await lerErro(r));
  return (await r.json()) as T;
}

/** Para páginas públicas: sem sessão devolve null em vez de redirecionar. */
export async function apiServidorOpcional<T>(caminho: string, init?: RequestInit): Promise<T | null> {
  const r = await chamar(caminho, init);
  if (r.status === 401) return null;
  if (r.status === 404) notFound();
  if (!r.ok) throw new Error(await lerErro(r));
  return (await r.json()) as T;
}
