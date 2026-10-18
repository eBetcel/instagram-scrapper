import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type Page } from "@playwright/test";

const [CONVITE_ANA, CONVITE_BIA] = JSON.parse(readFileSync(join(__dirname, ".convites.json"), "utf8"));
const rodada = Date.now();
// .test e outros domínios reservados são recusados pela validação de e-mail da api.
const ANA = `ana+${rodada}@exemplo.com`;
const BIA = `bia+${rodada}@exemplo.com`;

/** Link de login mais recente enviado para `email`, lido da api do Mailpit. */
async function linkDoMailpit(email: string): Promise<string> {
  for (let i = 0; i < 20; i++) {
    const busca = await fetch(`http://localhost:8025/api/v1/search?query=${encodeURIComponent(`to:"${email}"`)}`);
    const { messages } = await busca.json();
    if (messages?.length) {
      const msg = await (await fetch(`http://localhost:8025/api/v1/message/${messages[0].ID}`)).json();
      const link = msg.Text.match(/http\S+\/api\/auth\/verificar\?token=\S+/)?.[0];
      if (link) return link;
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`nenhum link para ${email} no Mailpit`);
}

async function criarContaEEntrar(page: Page, email: string, convite: string, nome: string) {
  await page.goto("/entrar");
  await page.getByLabel("E-mail").fill(email);
  await page.getByRole("button", { name: "Receber link de acesso" }).click();
  await page.getByLabel("Código de convite").fill(convite);
  await page.getByLabel("Seu nome").fill(nome);
  await page.getByRole("button", { name: "Criar conta e receber o link" }).click();
  await expect(page.getByText(`Enviamos um link para ${email}`)).toBeVisible();
  await page.goto(await linkDoMailpit(email));
  await expect(page).toHaveURL(/\/$/);
}

test("piloto: convite, grupo, agenda, página pública e seguir", async ({ page, browser }) => {
  // 1. Sem sessão, a agenda leva para /entrar.
  await page.goto("/");
  await expect(page).toHaveURL(/\/entrar$/);

  // 2–3. Ana cria a conta com convite e ainda não tem grupos.
  await criarContaEEntrar(page, ANA, CONVITE_ANA, "Ana");
  await expect(page.getByRole("link", { name: /Crie um grupo/ })).toBeVisible();

  // 4. Cria o grupo e adiciona @s.
  await page.goto("/grupos");
  await page.getByLabel("Nome", { exact: true }).fill("Agenda E2E");
  await page.getByRole("button", { name: "Criar grupo" }).click();
  await expect(page).toHaveURL(/\/g\/agenda-e2e$/);
  const adicionar = page.getByLabel("Adicionar @");
  for (const perfil of ["@casa_e2e", "perfil_novo_e2e", "nome inválido!"]) {
    await adicionar.fill(perfil);
    await page.getByRole("button", { name: "Adicionar", exact: true }).click();
  }
  // Nada é gravado antes de confirmar.
  await expect(page.getByText("Para confirmar")).toBeVisible();
  await page.getByRole("button", { name: "Confirmar (3)" }).click();
  await expect(page.getByText("@casa_e2e", { exact: true })).toBeVisible();
  await expect(page.getByText(/@perfil_novo_e2e · coletando…/)).toBeVisible();
  // O @ recusado fica na lista para corrigir ou descartar.
  await expect(page.getByText(/@nome inválido! · @ inválido/)).toBeVisible();
  await page.getByRole("button", { name: "descartar" }).click();
  await expect(page.getByText("Para confirmar")).toBeHidden();

  // 5. A agenda mostra o evento do @.
  await page.goto("/");
  const card = page.getByRole("article").filter({ hasText: "Show de Teste E2E" });
  await expect(card).toBeVisible();
  await expect(card).toContainText("21:00");

  // 6. Detalhe do evento.
  await card.getByRole("link", { name: "Show de Teste E2E" }).click();
  await expect(page).toHaveURL(/\/evento\/\d+$/);
  await expect(page.getByText("Divulgado por")).toBeVisible();
  await expect(page.getByRole("link", { name: "@casa_e2e" })).toBeVisible();

  // 7. Bia abre a página pública sem login, entra e segue.
  const bia = await (await browser.newContext()).newPage();
  await bia.goto("/g/agenda-e2e");
  await expect(bia.getByText(/Curadoria de Ana/)).toBeVisible();
  await expect(bia.getByText("Show de Teste E2E")).toBeVisible();
  await bia.getByRole("link", { name: "Seguir" }).click();
  await expect(bia).toHaveURL(/\/entrar$/);
  await criarContaEEntrar(bia, BIA, CONVITE_BIA, "Bia");
  await bia.goto("/g/agenda-e2e");
  await bia.getByRole("button", { name: "Seguir" }).click();
  await expect(bia.getByRole("button", { name: "Deixar de seguir" })).toBeVisible();
  await bia.goto("/");
  await expect(bia.getByText("Show de Teste E2E")).toBeVisible();

  // 8. Bia sai e perde o acesso à agenda.
  await bia.goto("/conta");
  await bia.getByRole("button", { name: "Sair" }).click();
  await expect(bia).toHaveURL(/\/entrar$/);
  await bia.goto("/");
  await expect(bia).toHaveURL(/\/entrar$/);
});
