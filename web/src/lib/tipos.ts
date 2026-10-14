// Espelho dos formatos da api (spec da Fatia 2, seção 7). Decimais chegam como string.

export type Categoria =
  | "show" | "festa" | "exposicao" | "teatro" | "cinema" | "oficina" | "festival" | "outro";

export type Evento = {
  id: number;
  titulo: string;
  inicio: string;
  hora_definida: boolean;
  fim: string | null;
  local_nome: string | null;
  cidade: string | null;
  categoria: Categoria;
  preco_texto: string | null;
  gratuito: boolean | null;
  preco_min: string | null;
  preco_max: string | null;
  link_ingresso: string | null;
  status: "ativo" | "adiado" | "cancelado" | "esgotado";
  festival: string | null;
  artistas: string[];
  alterado: boolean;
  imagem: string | null;
};

export type Fonte = {
  username: string;
  shortcode: string;
  url_instagram: string;
  publicado_em: string | null;
  decisao: "novo" | "duplicado" | "atualizacao";
};

export type Revisao = {
  campo: string;
  valor_anterior: string | null;
  valor_novo: string | null;
  motivo: string | null;
  criado_em: string;
};

export type EventoDetalhe = Evento & {
  descricao: string | null;
  endereco: string | null;
  fontes: Fonte[];
  revisoes: Revisao[];
};

export type Grupo = {
  slug: string;
  nome: string;
  descricao: string | null;
  curador: string;
  n_perfis: number;
  n_seguidores: number;
};

export type PerfilNoGrupo = {
  username: string;
  status: "ativo" | "coletando" | "privado" | "inexistente";
};

export type GrupoDetalhe = Grupo & {
  perfis: PerfilNoGrupo[];
  eventos: Evento[];
  sou_dono: boolean;
  sigo: boolean;
};

export type Usuario = { id: number; email: string; nome: string };
