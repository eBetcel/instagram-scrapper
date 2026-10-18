import type { ReactNode } from "react";

export function Vazio({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-linha p-4 text-sm text-texto">
      {children}
    </div>
  );
}
