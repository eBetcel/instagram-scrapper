import type { ReactNode } from "react";
import { classesChip } from "./estilos";

export function Chip({
  ativo,
  onClick,
  children,
}: {
  ativo: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button type="button" aria-pressed={ativo} onClick={onClick} className={classesChip(ativo)}>
      {children}
    </button>
  );
}
