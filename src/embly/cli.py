from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from embly.categories import CategoryService
from embly.classify import LayaEngine, build_state
from embly.config import (
    SETTABLE_KEYS,
    Config,
    format_value,
    get_dotted,
    load_config,
    load_raw,
    parse_value,
    resolve_config_path,
    save_raw,
    set_dotted_raw,
)
from embly.db import connect
from embly.extract import TextExtractor
from embly.extract.base import gather
from embly.ingest import Ingester, IngestResult

app = typer.Typer(no_args_is_help=True, add_completion=False)
cats_app = typer.Typer(no_args_is_help=True)
config_app = typer.Typer(no_args_is_help=True)
app.add_typer(cats_app, name="categories")
app.add_typer(config_app, name="config")
err = Console(stderr=True)
out = Console()


@dataclass(frozen=True)
class _Services:
    cfg: Config
    conn: sqlite3.Connection
    extractor: TextExtractor
    engine: LayaEngine
    categories: CategoryService
    ingester: Ingester


def _services(config: Optional[Path]) -> _Services:
    try:
        cfg = load_config(config)
    except Exception as e:  # noqa: BLE001
        err.print(f"[red]config error:[/red] {e}")
        raise typer.Exit(1) from e
    conn = connect(cfg.paths.db)
    extractor = TextExtractor(cfg.ocr, media=cfg.media)
    engine = LayaEngine(cfg.classify)
    categories = CategoryService(conn, embed=engine.embed, clear_embed_cache=engine.clear_cache)
    ingester = Ingester(conn, extractor, engine, categories, cfg.paths, cfg.classify)
    return _Services(cfg=cfg, conn=conn, extractor=extractor, engine=engine,
                     categories=categories, ingester=ingester)


def _print_table(rows: list[IngestResult]) -> None:
    table = Table(show_header=True, header_style="bold")
    for column in ("file", "category", "conf", "status", "ms", "source"):
        table.add_column(column)
    for row in rows:
        confidence = f"{row.confidence:.3f}" if isinstance(row.confidence, float) else "—"
        table.add_row(row.file, row.category or "—", confidence, row.status,
                      f"{row.ms:.0f}", row.source or "—")
    out.print(table)


@app.command()
def status(config: Annotated[Optional[Path], typer.Option(help="config.toml")] = None) -> None:
    services = _services(config)
    cfg = services.cfg
    schema_row = services.conn.execute(
        "SELECT value FROM meta WHERE key='schema_version'"
    ).fetchone()
    schema_version = schema_row["value"] if schema_row else "?"
    out.print(f"[bold]root[/bold]    {cfg.paths.root}")
    out.print(f"[bold]inbox[/bold]   {cfg.paths.inbox}")
    out.print(f"[bold]db[/bold]      {cfg.paths.db} (schema v{schema_version})")
    try:
        import torch

        device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
    except Exception:  # noqa: BLE001
        device = "unknown"
    ocr = "yes" if find_spec("paddleocr") else "no"
    out.print(f"[bold]device[/bold]  {device}   [bold]ocr[/bold] {ocr}   [bold]langs[/bold] {','.join(cfg.ocr.langs)}")
    out.print(f"[bold]ocr.engine[/bold]  {cfg.ocr.engine}")
    out.print(f"[bold]whisper[/bold]  {cfg.media.whisper_model} "
              f"({cfg.media.whisper_device}/{cfg.media.whisper_compute_type})")
    out.print(f"[bold]classify[/bold]  {cfg.classify.model}#{cfg.classify.subfolder} "
              f"(router={cfg.classify.router_default}, device={cfg.classify.device})")
    out.print(f"[bold]naming_llm[/bold]  {cfg.naming_llm.model} @ {cfg.naming_llm.host} [{cfg.naming_llm.mode}]")
    for row in services.conn.execute("SELECT status, COUNT(*) n FROM files GROUP BY status ORDER BY status"):
        out.print(f"  files.{row['status']:<11} {row['n']}")
    for cc in services.categories.counts():
        out.print(f"  cat.{cc.slug:<13} {cc.count}")


@app.command()
def ingest(
    path: Annotated[Path, typer.Argument(help="file or directory")],
    config: Annotated[Optional[Path], typer.Option(help="config.toml")] = None,
) -> None:
    services = _services(config)
    services.cfg.ensure_dirs()
    active = services.categories.list_active()
    if not active:
        err.print("[yellow]no categories yet — files will be recorded as 'novel'.[/yellow]")
        err.print("[yellow]create some first: embly categories add <name> --desc '...'[/yellow]")
    files = gather([path])
    if not files:
        err.print("[red]no files found[/red]")
        raise typer.Exit(1)
    err.print(f"{len(files)} file(s), {len(active)} category(ies)")
    _print_table(services.ingester.ingest_many(files))


@app.command()
def classify(
    file: Annotated[Path, typer.Argument(help="file to classify (read-only)")],
    config: Annotated[Optional[Path], typer.Option(help="config.toml")] = None,
) -> None:
    services = _services(config)
    active = services.categories.list_active()
    if not active:
        err.print("[red]no categories. add some: embly categories add <name> --desc '...'[/red]")
        raise typer.Exit(1)
    extraction = services.extractor.extract(file)
    if not extraction.text.strip():
        err.print(f"[red]no extractable text ({extraction.source})[/red]")
        raise typer.Exit(1)
    state = build_state(file.name, extraction.text, services.cfg.classify.max_text_tokens)
    decision = services.engine.decide(state, active)
    out.print(f"category={decision.choice}  answer_confidence={decision.confidence:.3f}  "
              f"model={decision.model}  {decision.ms:.0f}ms  ({extraction.source})")


@cats_app.command("add")
def cats_add(
    name: Annotated[str, typer.Argument()],
    desc: Annotated[str, typer.Option("--desc", help="criteria text (drives accuracy)")],
    config: Annotated[Optional[Path], typer.Option(help="config.toml")] = None,
) -> None:
    services = _services(config)
    category = services.categories.add(name, desc)
    out.print(f"added [green]{category.slug}[/green] (id={category.id})")


@cats_app.command("list")
def cats_list(config: Annotated[Optional[Path], typer.Option(help="config.toml")] = None) -> None:
    services = _services(config)
    for category in services.categories.list_active():
        out.print(f"[green]{category.slug}[/green] — {category.description}")


@cats_app.command("show")
def cats_show(
    name: Annotated[str, typer.Argument()],
    config: Annotated[Optional[Path], typer.Option(help="config.toml")] = None,
) -> None:
    services = _services(config)
    category = services.categories.get(name)
    if category is None:
        err.print(f"[red]unknown category: {name}[/red]")
        raise typer.Exit(1)
    count = services.categories.file_count(category.id)
    out.print(f"slug        {category.slug}")
    out.print(f"name        {category.name}")
    out.print(f"description {category.description}")
    out.print(f"status      {category.status}  auto_created={category.auto_created}")
    out.print(f"files       {count}")


@cats_app.command("describe")
def cats_describe(
    name: Annotated[str, typer.Argument()],
    desc: Annotated[str, typer.Option("--desc", help="new criteria text")],
    config: Annotated[Optional[Path], typer.Option(help="config.toml")] = None,
) -> None:
    services = _services(config)
    category = services.categories.describe(name, desc)
    out.print(f"updated [green]{category.slug}[/green]")


@config_app.command("list")
def config_list(config: Annotated[Optional[Path], typer.Option(help="config.toml")] = None) -> None:
    """Show all CLI-settable model/setting keys with current values."""
    cfg = load_config(config)
    table = Table(show_header=True, header_style="bold")
    table.add_column("key")
    table.add_column("value")
    for key in sorted(SETTABLE_KEYS):
        try:
            table.add_row(key, format_value(get_dotted(cfg, key)))
        except Exception:  # noqa: BLE001
            table.add_row(key, "?")
    out.print(table)
    out.print(f"[dim]file: {resolve_config_path(config)}[/dim]")


@config_app.command("get")
def config_get(
    key: Annotated[str, typer.Argument(help="dotted key, e.g. media.whisper_model")],
    config: Annotated[Optional[Path], typer.Option(help="config.toml")] = None,
) -> None:
    """Print one config value."""
    if key not in SETTABLE_KEYS:
        err.print(f"[red]unknown key: {key}[/red] (see `embly config list`)")
        raise typer.Exit(1)
    out.print(format_value(get_dotted(load_config(config), key)))


@config_app.command("set")
def config_set(
    key: Annotated[str, typer.Argument(help="dotted key, e.g. media.whisper_model")],
    value: Annotated[str, typer.Argument(help="new value (lists: a,b,c or JSON array)")],
    config: Annotated[Optional[Path], typer.Option(help="config.toml")] = None,
) -> None:
    """Persist one model/setting value to config.toml."""
    if key not in SETTABLE_KEYS:
        err.print(f"[red]unknown key: {key}[/red] (see `embly config list`)")
        raise typer.Exit(1)
    _, _, kind = SETTABLE_KEYS[key]
    try:
        parsed = parse_value(kind, value)
    except Exception as e:  # noqa: BLE001
        err.print(f"[red]bad value for {key}:[/red] {e}")
        raise typer.Exit(1) from e
    if key == "ocr.engine" and parsed != "paddle":
        err.print("[yellow]warning: only 'paddle' is implemented — other engines will fail at ingest.[/yellow]")
    target = resolve_config_path(config, for_write=True)
    data = set_dotted_raw(load_raw(target), key, parsed)
    try:
        save_raw(target, data)
    except Exception as e:  # noqa: BLE001
        err.print(f"[red]could not write {target}:[/red] {e}")
        raise typer.Exit(1) from e
    # reload to prove the written file parses and coerces cleanly
    cfg = load_config(target)
    out.print(f"set [green]{key}[/green]={format_value(get_dotted(cfg, key))}  [dim]({target})[/dim]")


@config_app.command("path")
def config_path(config: Annotated[Optional[Path], typer.Option(help="config.toml")] = None) -> None:
    """Print which config.toml would be used."""
    out.print(str(resolve_config_path(config)))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
