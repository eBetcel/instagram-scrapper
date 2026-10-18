import type { SelectHTMLAttributes } from "react";
import { classesCampo } from "./estilos";

export function Seletor({
  className,
  children,
  ...resto
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative">
      <select
        {...resto}
        className={`${classesCampo(false)} appearance-none pr-9${className ? ` ${className}` : ""}`}
      >
        {children}
      </select>
      <svg
        aria-hidden="true"
        viewBox="0 0 20 20"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-apagado"
      >
        <path d="m5 7.5 5 5 5-5" />
      </svg>
    </div>
  );
}
