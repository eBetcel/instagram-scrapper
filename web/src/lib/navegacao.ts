export const ITENS_NAV = [
  { href: "/", rotulo: "Agenda" },
  { href: "/grupos", rotulo: "Grupos" },
  { href: "/conta", rotulo: "Conta" },
] as const;

const PREFIXOS: Record<string, readonly string[]> = {
  "/": ["/evento"],
  "/grupos": ["/grupos", "/g"],
  "/conta": ["/conta"],
};

function sob(pathname: string, base: string): boolean {
  return pathname === base || pathname.startsWith(base + "/");
}

export function itemAtivo(pathname: string, href: string): boolean {
  if (href === "/" && pathname === "/") return true;
  return (PREFIXOS[href] ?? [href]).some((base) => sob(pathname, base));
}
