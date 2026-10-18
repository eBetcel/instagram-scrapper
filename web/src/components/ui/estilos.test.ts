import { describe, expect, it } from "vitest";
import {
  classesAviso,
  classesBotao,
  classesCampo,
  classesChip,
  classesSelo,
  foco,
} from "./estilos";

describe("classesCampo", () => {
  it("tem 44px, fundo superficie e borda linha", () => {
    const c = classesCampo(false);
    expect(c).toContain("min-h-11");
    expect(c).toContain("bg-superficie");
    expect(c).toContain("border-linha");
    expect(c).toContain("focus-visible:border-acento");
  });
  it("com erro troca a borda para erro", () => {
    expect(classesCampo(true)).toContain("border-erro");
    expect(classesCampo(true)).not.toContain("border-linha");
  });
});

describe("classesBotao", () => {
  it("primario usa o acento como fundo e o texto sobre-acento", () => {
    const c = classesBotao("primario");
    expect(c).toContain("bg-acento");
    expect(c).toContain("text-sobre-acento");
    expect(c).toContain("active:bg-acento-forte");
  });
  it("md tem 44px e sm tem 36px", () => {
    expect(classesBotao("primario", "md")).toContain("min-h-11");
    expect(classesBotao("primario", "sm")).toContain("min-h-9");
  });
  it("padrão é secundario md, com borda linha", () => {
    const c = classesBotao();
    expect(c).toContain("border-linha");
    expect(c).toContain("bg-superficie");
    expect(c).toContain("min-h-11");
  });
  it("fantasma e perigo não têm fundo", () => {
    expect(classesBotao("fantasma")).toContain("text-acento-forte");
    expect(classesBotao("perigo")).toContain("text-erro");
    expect(classesBotao("perigo")).not.toContain("bg-acento");
  });
  it("todas as variantes desabilitam com opacidade", () => {
    for (const v of ["primario", "secundario", "fantasma", "perigo"] as const) {
      expect(classesBotao(v)).toContain("disabled:opacity-50");
    }
  });
});

describe("classesChip", () => {
  it("ativo inverte para tinta", () => {
    expect(classesChip(true)).toContain("bg-tinta");
    expect(classesChip(true)).toContain("text-fundo");
  });
  it("inativo tem borda linha e não usa tinta de fundo", () => {
    expect(classesChip(false)).toContain("border-linha");
    expect(classesChip(false)).not.toContain("bg-tinta");
  });
  it("tem 36px de altura", () => expect(classesChip(false)).toContain("min-h-9"));
});

describe("classesSelo", () => {
  it("neutro usa suave, acento usa acento-forte", () => {
    expect(classesSelo("neutro")).toContain("bg-suave");
    expect(classesSelo("acento")).toContain("text-acento-forte");
  });
});

describe("classesAviso", () => {
  it("erro usa a cor de erro; info e sucesso usam a de sucesso", () => {
    expect(classesAviso("erro")).toContain("text-erro");
    expect(classesAviso("info")).toContain("text-sucesso");
    expect(classesAviso("sucesso")).toContain("text-sucesso");
  });
});

describe("foco", () => {
  it("usa anel sólido com offset", () => {
    expect(foco).toContain("ring-acento-forte");
    expect(foco).toContain("ring-offset-2");
  });
});
