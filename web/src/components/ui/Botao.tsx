import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { classesBotao, type TamanhoBotao, type VarianteBotao } from "./estilos";

type Comuns = {
  variante?: VarianteBotao;
  tamanho?: TamanhoBotao;
  className?: string;
  children: ReactNode;
};

type PropsLink = Comuns & { href: string; externo?: boolean };
type PropsBotao = Comuns & ButtonHTMLAttributes<HTMLButtonElement> & { href?: undefined };

export function Botao(props: PropsLink | PropsBotao) {
  const { variante, tamanho, className, children } = props;
  const classes = `${classesBotao(variante, tamanho)}${className ? ` ${className}` : ""}`;

  if (props.href !== undefined) {
    if (props.externo) {
      return (
        <a href={props.href} target="_blank" rel="noopener noreferrer" className={classes}>
          {children}
        </a>
      );
    }
    return (
      <Link href={props.href} className={classes}>
        {children}
      </Link>
    );
  }

  const { type = "button", ...resto } = props;
  const html: Record<string, unknown> = { ...resto };
  for (const k of ["variante", "tamanho", "className", "children", "href"]) delete html[k];
  return (
    <button type={type} className={classes} {...(html as ButtonHTMLAttributes<HTMLButtonElement>)}>
      {children}
    </button>
  );
}
