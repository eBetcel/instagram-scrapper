import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { Fraunces, Inter } from "next/font/google";
import NavPrincipal from "@/components/NavPrincipal";
import "./globals.css";

const fraunces = Fraunces({ subsets: ["latin"], variable: "--font-fraunces", display: "swap" });
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Agenda", template: "%s · Agenda" },
  description: "A agenda cultural dos perfis que você acompanha no Instagram.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="pt-BR" className={`${fraunces.variable} ${inter.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-fundo text-texto font-sans">
        <header className="sticky top-0 z-20 h-14 border-b border-linha bg-fundo/90 backdrop-blur">
          <div className="mx-auto flex h-full max-w-2xl items-center px-4">
            <Link href="/" className="mr-auto font-serifa text-xl tracking-[-0.01em] text-tinta">
              Agenda
            </Link>
            <Suspense fallback={null}>
              <NavPrincipal variante="topo" />
            </Suspense>
          </div>
        </header>
        <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-6 pb-24 md:pb-6">{children}</main>
        <Suspense fallback={null}>
          <NavPrincipal variante="inferior" />
        </Suspense>
      </body>
    </html>
  );
}
