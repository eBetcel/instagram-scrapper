import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const redirect = vi.fn((url: string) => {
  throw new Error(`REDIRECT ${url}`);
});
const notFound = vi.fn(() => {
  throw new Error("NOT_FOUND");
});
vi.mock("next/navigation", () => ({ redirect, notFound }));
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: (n: string) => (n === "sessao" ? { value: "abc" } : undefined) }),
}));

const { apiServidor, apiServidorOpcional } = await import("./api-servidor");

function resposta(status: number, corpo: unknown) {
  return new Response(JSON.stringify(corpo), { status, headers: { "content-type": "application/json" } });
}

describe("apiServidor", () => {
  const fetchFalso = vi.fn();
  beforeEach(() => {
    vi.stubGlobal("fetch", fetchFalso);
    process.env.API_URL_INTERNA = "http://api:8010";
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    fetchFalso.mockReset();
  });

  it("repassa o cookie de sessão para a api interna", async () => {
    fetchFalso.mockResolvedValue(resposta(200, { id: 1 }));
    expect(await apiServidor("/api/eu")).toEqual({ id: 1 });
    const [url, init] = fetchFalso.mock.calls[0];
    expect(url).toBe("http://api:8010/api/eu");
    expect(new Headers(init.headers).get("cookie")).toBe("sessao=abc");
    expect(init.cache).toBe("no-store");
  });

  it("401 manda para /entrar", async () => {
    fetchFalso.mockResolvedValue(resposta(401, { detail: "Faça login" }));
    await expect(apiServidor("/api/eu")).rejects.toThrow("REDIRECT /entrar");
  });

  it("404 vira notFound", async () => {
    fetchFalso.mockResolvedValue(resposta(404, { detail: "x" }));
    await expect(apiServidor("/api/eventos/9")).rejects.toThrow("NOT_FOUND");
  });

  it("outro erro lança com a mensagem da api", async () => {
    fetchFalso.mockResolvedValue(resposta(422, { detail: "Grupo inválido" }));
    await expect(apiServidor("/api/grupos")).rejects.toThrow("Grupo inválido");
  });

  it("opcional devolve null sem sessão", async () => {
    fetchFalso.mockResolvedValue(resposta(401, { detail: "Faça login" }));
    expect(await apiServidorOpcional("/api/eu")).toBeNull();
  });
});
