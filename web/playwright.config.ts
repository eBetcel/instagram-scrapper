import { defineConfig, devices } from "@playwright/test";

// Stack de teste: api na 8111 com o banco agenda_e2e e o front na 3101 (build próprio,
// porque os rewrites para a api são fixados no build). E-mails no Mailpit (8025).
const DATABASE_URL = "postgresql+psycopg://agenda:agenda@localhost:5432/agenda_e2e";

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  use: { baseURL: "http://localhost:3101", ...devices["Pixel 7"], trace: "retain-on-failure" },
  webServer: [
    {
      command: "uv run --project ../backend agenda api --porta 8111",
      url: "http://localhost:8111/api/openapi.json",
      env: { DATABASE_URL, APP_URL: "http://localhost:3101" },
      reuseExistingServer: false,
    },
    {
      command: "npx next build && npx next start -p 3101",
      url: "http://localhost:3101/entrar",
      env: { API_URL_INTERNA: "http://localhost:8111" },
      timeout: 180_000,
      reuseExistingServer: false,
    },
  ],
});
