"""Comando `agenda avaliar` (não roda no CI nem no pytest; chama a OpenAI de verdade)."""

from pathlib import Path
from typing import Annotated

import typer

from agenda.config import get_settings


def avaliar(
    etapa: Annotated[str, typer.Option(help="extracao ou reconciliacao.")],
    golden: Annotated[Path, typer.Option(help="Diretório com os casos (ex.: backend/golden/casos).")],
) -> None:
    """Avalia a extração ou a reconciliação contra o golden set e imprime o relatório."""
    from agenda.avaliacao.golden import avaliar_extracao, avaliar_reconciliacao, carregar_casos

    if etapa not in ("extracao", "reconciliacao"):
        typer.echo(f"Etapa inválida: {etapa!r} (use extracao ou reconciliacao).", err=True)
        raise typer.Exit(1)
    if not golden.is_dir():
        typer.echo(f"Diretório não encontrado: {golden}", err=True)
        raise typer.Exit(1)
    settings = get_settings()
    if not settings.openai_api_key:
        typer.echo("OPENAI_API_KEY não configurada.", err=True)
        raise typer.Exit(1)
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    casos = carregar_casos(golden)
    if etapa == "extracao":
        from agenda.extracao.extrator import OpenAIExtrator

        relatorio = avaliar_extracao(casos, OpenAIExtrator(client, settings.openai_modelo_extracao))
    else:
        from agenda.reconciliacao.decisao import OpenAIReconciliador

        relatorio = avaliar_reconciliacao(
            casos, OpenAIReconciliador(client, settings.openai_modelo_reconciliacao)
        )
    typer.echo(relatorio.formatar())
