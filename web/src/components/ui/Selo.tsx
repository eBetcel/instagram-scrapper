import type { ReactNode } from "react";
import { classesSelo, type TomSelo } from "./estilos";

export function Selo({ tom, children }: { tom?: TomSelo; children: ReactNode }) {
  return <span className={classesSelo(tom)}>{children}</span>;
}
