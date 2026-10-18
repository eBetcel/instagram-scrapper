import type { Metadata } from "next";
import { Suspense } from "react";
import { ListaPorDia } from "@/components/ListaPorDia";
import { Carregando } from "@/components/ui/Carregando";
import { Selo } from "@/components/ui/Selo";
import { Titulo } from "@/components/ui/Titulo";
import { Vazio } from "@/components/ui/Vazio";
import { apiServidorOpcional } from "@/lib/api-servidor";
import { STATUS_PERFIL as STATUS } from "@/lib/formato";
import type { GrupoDetalhe, Usuario } from "@/lib/tipos";
import { BotaoSeguir } from "./BotaoSeguir";
import { EditorGrupo } from "./EditorGrupo";

type Params = PageProps<"/g/[slug]">["params"];

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { slug } = await params;
  const base = process.env.API_URL_INTERNA ?? "http://localhost:8010";
  const r = await fetch(`${base}/api/grupos/${encodeURIComponent(slug)}`, { cache: "no-store" });
  if (!r.ok) return { title: "Grupo" };
  const g: GrupoDetalhe = await r.json();
  const description = g.descricao || `Agenda cultural de ${g.nome}`;
  return { title: g.nome, description, openGraph: { title: g.nome, description, type: "website" } };
}

async function Conteudo({ params }: { params: Params }) {
  const { slug } = await params;
  const [g, eu] = await Promise.all([
    apiServidorOpcional<GrupoDetalhe>(`/api/grupos/${encodeURIComponent(slug)}`),
    apiServidorOpcional<Usuario>("/api/eu"),
  ]);
  if (!g) return null; // a rota é pública: sem sessão não há 401
  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <Titulo nivel={1}>{g.nome}</Titulo>
        {g.descricao && <p className="text-texto">{g.descricao}</p>}
        <p className="text-sm text-apagado">
          Curadoria de {g.curador} · {g.n_seguidores} seguidor{g.n_seguidores === 1 ? "" : "es"}
        </p>
        {!g.sou_dono && <BotaoSeguir slug={g.slug} logado={eu !== null} sigo={g.sigo} />}
      </header>
      {g.sou_dono ? (
        <EditorGrupo grupo={g} />
      ) : (
        <section className="space-y-1">
          <Titulo nivel={2}>Perfis</Titulo>
          <ul className="flex flex-wrap gap-2 text-sm">
            {g.perfis.map((p) => (
              <li key={p.username}>
                <Selo tom="neutro">
                  @{p.username}{STATUS[p.status] && <span className="text-apagado"> · {STATUS[p.status]}</span>}
                </Selo>
              </li>
            ))}
          </ul>
        </section>
      )}
      <section className="space-y-2">
        <Titulo nivel={2}>Próximos eventos</Titulo>
        {g.eventos.length === 0 ? (
          <Vazio>Nenhum evento nos próximos 30 dias.</Vazio>
        ) : (
          <ListaPorDia eventos={g.eventos} />
        )}
      </section>
    </div>
  );
}

export default function PaginaDoGrupo({ params }: PageProps<"/g/[slug]">) {
  return (
    <Suspense fallback={<Carregando />}>
      <Conteudo params={params} />
    </Suspense>
  );
}
