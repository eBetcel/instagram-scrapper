import type { NextConfig } from "next";

const API_URL_INTERNA = process.env.API_URL_INTERNA ?? "http://localhost:8010";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // O navegador só fala com esta origem: /api/* vai para a api, e o cookie de sessão
  // fica nesta origem também.
  async rewrites() {
    return [{ source: "/api/:caminho*", destination: `${API_URL_INTERNA}/api/:caminho*` }];
  },
};

export default nextConfig;
