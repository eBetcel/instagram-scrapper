import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { chamarApi } from "./api-cliente";

describe("chamarApi", () => {
  const fetchFalso = vi.fn();
  beforeEach(() => vi.stubGlobal("fetch", fetchFalso));
  afterEach(() => {
    vi.unstubAllGlobals();
    fetchFalso.mockReset();
  });

  it("202 é ok, na mesma origem", async () => {
    fetchFalso.mockResolvedValue(new Response(JSON.stringify({ detail: "Link enviado" }), { status: 202 }));
    const r = await chamarApi("/auth/entrar", { method: "POST", body: "{}" });
    expect(r).toEqual({ ok: true, dados: { detail: "Link enviado" } });
    const [url, init] = fetchFalso.mock.calls[0];
    expect(url).toBe("/api/auth/entrar");
    expect(init.credentials).toBe("same-origin");
    expect(new Headers(init.headers).get("content-type")).toBe("application/json");
  });

  it("409 traz status, mensagem e corpo", async () => {
    fetchFalso.mockResolvedValue(new Response(JSON.stringify({ detail: "Informe o convite", precisa_convite: true }), { status: 409 }));
    const r = await chamarApi("/auth/entrar");
    expect(r).toMatchObject({ ok: false, status: 409, mensagem: "Informe o convite", corpo: { precisa_convite: true } });
  });

  it("resposta sem JSON vira mensagem genérica", async () => {
    fetchFalso.mockResolvedValue(new Response("<html>502</html>", { status: 502 }));
    expect(await chamarApi("/x")).toMatchObject({ ok: false, status: 502, mensagem: "Algo deu errado. Tente de novo." });
  });

  it("204 é ok sem corpo", async () => {
    fetchFalso.mockResolvedValue(new Response(null, { status: 204 }));
    expect(await chamarApi("/auth/sair", { method: "POST" })).toEqual({ ok: true, dados: null });
  });

  it("falha de rede vira mensagem genérica", async () => {
    fetchFalso.mockRejectedValue(new TypeError("fetch failed"));
    expect(await chamarApi("/x")).toMatchObject({ ok: false, status: 0, mensagem: "Algo deu errado. Tente de novo." });
  });

  it("erro de validação do FastAPI (lista) vira mensagem para conferir os dados", async () => {
    const detail = [{ loc: ["body", "email"], msg: "value is not a valid email address", type: "value_error" }];
    fetchFalso.mockResolvedValue(new Response(JSON.stringify({ detail }), { status: 422 }));
    expect(await chamarApi("/auth/entrar")).toMatchObject({ ok: false, status: 422, mensagem: "Confira os dados informados." });
  });
});
