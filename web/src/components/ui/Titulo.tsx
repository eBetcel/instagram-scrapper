import type { ReactNode } from "react";

const h1 =
  "font-serifa text-[30px] md:text-[32px] leading-tight tracking-[-0.02em] text-tinta";
const h2 = "font-serifa text-xl tracking-[-0.01em] text-tinta";

export function Titulo({
  nivel,
  className,
  children,
}: {
  nivel: 1 | 2;
  className?: string;
  children: ReactNode;
}) {
  const extra = className ? ` ${className}` : "";
  return nivel === 1 ? (
    <h1 className={`${h1}${extra}`}>{children}</h1>
  ) : (
    <h2 className={`${h2}${extra}`}>{children}</h2>
  );
}
