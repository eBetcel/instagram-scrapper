"use client";

import { useState } from "react";
import { Aviso } from "@/components/ui/Aviso";
import { Botao } from "@/components/ui/Botao";
import { Campo } from "@/components/ui/Campo";
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
      <Campo rotulo="E-mail" type="email" required autoComplete="email" value={email}
        onChange={(e) => setEmail(e.target.value)} readOnly={etapa === "convite"} />
      {etapa === "convite" && (
        <>
          <p className="text-sm text-texto">É a sua primeira vez por aqui: informe o código de convite que você recebeu.</p>
          <Campo rotulo="Código de convite" required value={convite} onChange={(e) => setConvite(e.target.value)}
            placeholder="XXXX-XXXX" autoCapitalize="characters" />
          <Campo rotulo="Seu nome" required maxLength={60} autoComplete="name" value={nome}
            onChange={(e) => setNome(e.target.value)} />
        </>
      )}
      {erro && <Aviso>{erro}</Aviso>}
      <Botao variante="primario" type="submit" disabled={enviando} className="w-full">
        {enviando ? "Enviando…" : etapa === "convite" ? "Criar conta e receber o link" : "Receber link de acesso"}
      </Botao>
    </form>
  );
}
