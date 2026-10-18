"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { foco } from "@/components/ui/estilos";
import { ITENS_NAV, itemAtivo } from "@/lib/navegacao";

const icone = {
  width: 24,
  height: 24,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
} as const;

const ICONES: Record<string, ReactNode> = {
  "/": (
    <svg {...icone}>
      <rect x="3.5" y="5" width="17" height="15.5" rx="2" />
      <path d="M3.5 10h17M8 3v4M16 3v4" />
    </svg>
  ),
  "/grupos": (
    <svg {...icone}>
      <circle cx="12" cy="8" r="3" />
      <circle cx="5.5" cy="10" r="2.25" />
      <circle cx="18.5" cy="10" r="2.25" />
      <path d="M6.5 19c0-3 2.5-5 5.5-5s5.5 2 5.5 5M1.5 18c0-2 1.5-3.5 3.5-3.5M22.5 18c0-2-1.5-3.5-3.5-3.5" />
    </svg>
  ),
  "/conta": (
    <svg {...icone}>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="10" r="3" />
      <path d="M6.5 18.5c1.2-2.2 3.2-3.2 5.5-3.2s4.3 1 5.5 3.2" />
    </svg>
  ),
};

export default function NavPrincipal({ variante }: { variante: "topo" | "inferior" }) {
  const pathname = usePathname();

  if (variante === "topo") {
    return (
      <nav aria-label="Principal" className="hidden md:flex items-center gap-6">
        {ITENS_NAV.map(({ href, rotulo }) => {
          const ativo = itemAtivo(pathname, href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={ativo ? "page" : undefined}
              className={`rounded-lg text-sm font-medium ${foco} ${
                ativo
                  ? "text-tinta underline decoration-acento decoration-2 underline-offset-[6px]"
                  : "text-apagado"
              }`}
            >
              {rotulo}
            </Link>
          );
        })}
      </nav>
    );
  }

  return (
    <nav
      aria-label="Principal"
      className="md:hidden fixed inset-x-0 bottom-0 z-20 flex bg-superficie border-t border-linha pb-[env(safe-area-inset-bottom)]"
    >
      {ITENS_NAV.map(({ href, rotulo }) => {
        const ativo = itemAtivo(pathname, href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={ativo ? "page" : undefined}
            className={`flex-1 flex flex-col items-center justify-center h-14 gap-0.5 text-xs font-medium ${foco} ${
              ativo ? "text-acento-forte" : "text-apagado"
            }`}
          >
            {ICONES[href]}
            {rotulo}
          </Link>
        );
      })}
    </nav>
  );
}
