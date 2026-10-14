export function Aviso({ tipo = "erro", children }: { tipo?: "erro" | "info"; children: React.ReactNode }) {
  const cor = tipo === "erro" ? "border-red-200 bg-red-50 text-red-800" : "border-emerald-200 bg-emerald-50 text-emerald-900";
  return <p role={tipo === "erro" ? "alert" : "status"} className={`rounded-md border px-3 py-2 text-sm ${cor}`}>{children}</p>;
}
