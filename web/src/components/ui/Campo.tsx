"use client";

import { useId } from "react";
import type { InputHTMLAttributes, TextareaHTMLAttributes } from "react";
import { classesCampo } from "./estilos";

type Extras = { rotulo?: string; erro?: string };

function Rotulo({ id, rotulo }: { id: string; rotulo?: string }) {
  if (!rotulo) return null;
  return (
    <label htmlFor={id} className="text-[13px] font-medium text-texto">
      {rotulo}
    </label>
  );
}

function Erro({ id, erro }: { id: string; erro?: string }) {
  if (!erro) return null;
  return (
    <p id={`${id}-erro`} className="text-sm text-erro">
      {erro}
    </p>
  );
}

export function Campo({
  rotulo,
  erro,
  className,
  ...resto
}: InputHTMLAttributes<HTMLInputElement> & Extras) {
  const gerado = useId();
  const id = resto.id ?? gerado;
  return (
    <div className="flex flex-col gap-1.5">
      <Rotulo id={id} rotulo={rotulo} />
      <input
        {...resto}
        id={id}
        aria-invalid={erro ? true : undefined}
        aria-describedby={erro ? `${id}-erro` : resto["aria-describedby"]}
        className={`${classesCampo(!!erro)}${className ? ` ${className}` : ""}`}
      />
      <Erro id={id} erro={erro} />
    </div>
  );
}

export function AreaTexto({
  rotulo,
  erro,
  className,
  ...resto
}: TextareaHTMLAttributes<HTMLTextAreaElement> & Extras) {
  const gerado = useId();
  const id = resto.id ?? gerado;
  return (
    <div className="flex flex-col gap-1.5">
      <Rotulo id={id} rotulo={rotulo} />
      <textarea
        {...resto}
        id={id}
        aria-invalid={erro ? true : undefined}
        aria-describedby={erro ? `${id}-erro` : resto["aria-describedby"]}
        className={`${classesCampo(!!erro)}${className ? ` ${className}` : ""}`}
      />
      <Erro id={id} erro={erro} />
    </div>
  );
}
