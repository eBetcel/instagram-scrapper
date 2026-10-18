import type { HTMLAttributes, ReactNode } from "react";

type Props = {
  as?: "div" | "article" | "section" | "form" | "ul";
  className?: string;
  children?: ReactNode;
} & HTMLAttributes<HTMLElement>;

export function Cartao({ as: Tag = "div", className, children, ...resto }: Props) {
  return (
    <Tag
      {...resto}
      className={`bg-superficie border border-linha rounded-xl shadow-[0_1px_3px_rgb(20_20_19/0.06)] dark:shadow-none${className ? ` ${className}` : ""}`}
    >
      {children}
    </Tag>
  );
}
