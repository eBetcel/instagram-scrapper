import type { ReactNode } from "react";
import { classesAviso, type TipoAviso } from "./estilos";

export function Aviso({ tipo = "erro", children }: { tipo?: TipoAviso; children: ReactNode }) {
  return (
    <p role={tipo === "erro" ? "alert" : "status"} className={classesAviso(tipo)}>
      {children}
    </p>
  );
}
