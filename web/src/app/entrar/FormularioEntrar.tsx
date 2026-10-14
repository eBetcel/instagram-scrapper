"use client";

import { useState } from "react";
import { Aviso } from "@/components/Aviso";
import { campo } from "@/components/campos";
import { chamarApi } from "@/lib/api-cliente";

type Etapa = "email" | "convite" | "enviado";



export function FormularioEntrar() {
  const [etapa, setEtapa] = useState<Etapa>("email");
  const [email, setEmail] = useState("");
  const [convite, setConvite] = useState("");
  const [nome, setNome] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    setEnviando(true);
    const corpo = etapa === "convite" ? { email, convite, nome } : { email };
    const r = await chamarApi("/auth/entrar", { method: "POST", body: JSON.stringify(corpo) });
    setEnviando(false);
    if (r.ok) return setEtapa("enviado");
    if (r.status === 409 && (r.corpo as { precisa_convite?: boolean })?.precisa_convite) {
      return setEtapa("convite");
    }
    setErro(r.mensagem);
  }

  if (etapa === "enviado") {
    return <Aviso tipo="info">Enviamos um link para {email}. Ele vale por 15 minutos.</Aviso>;
  }

  return (
    <form onSubmit={enviar} className="space-y-3">
      <label className="block space-y-1 text-sm">
        <span>E-mail</span>
        <input type="email" required autoComplete="email" value={email}
          onChange={(e) => setEmail(e.target.value)} readOnly={etapa === "convite"} className={campo} />
      </label>
      {etapa === "convite" && (
        <>
          <p className="text-sm text-stone-600">É a sua primeira vez por aqui: informe o código de convite que você recebeu.</p>
          <label className="block space-y-1 text-sm">
            <span>Código de convite</span>
            <input required value={convite} onChange={(e) => setConvite(e.target.value)}
              placeholder="XXXX-XXXX" autoCapitalize="characters" className={campo} />
          </label>
          <label className="block space-y-1 text-sm">
            <span>Seu nome</span>
            <input required maxLength={60} autoComplete="name" value={nome}
              onChange={(e) => setNome(e.target.value)} className={campo} />
          </label>
        </>
      )}
      {erro && <Aviso>{erro}</Aviso>}
      <button type="submit" disabled={enviando}
        className="w-full rounded-md bg-stone-900 px-3 py-2 font-medium text-white disabled:opacity-50">
        {enviando ? "Enviando…" : etapa === "convite" ? "Criar conta e receber o link" : "Receber link de acesso"}
      </button>
    </form>
  );
}
