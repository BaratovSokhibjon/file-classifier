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
from embly.classify import LayaEngine, NamingClient, build_state
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
from embly.discover import Discoverer, DiscoverReport
from embly.extract import TextExtractor
from embly.extract.base import gather
from embly.ingest import Ingester, IngestResult
from embly.organize import Organizer

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
    discoverer: Discoverer
    organizer: Organizer


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
    ingester = Ingester(conn, extractor, engine, categories, cfg.paths, cfg.classify,
                        novelty=cfg.novelty)
    discoverer = Discoverer(conn, engine, categories, NamingClient(cfg.naming_llm),
                           cfg.novelty, cfg.paths)
    organizer = Organizer(conn, categories, cfg.paths, cfg.naming)
    return _Services(cfg=cfg, conn=conn, extractor=extractor, engine=engine,
                     categories=categories, ingester=ingester, discoverer=discoverer,
                     organizer=organizer)


def _print_table(rows: list[IngestResult]) -> None:
    table = Table(show_header=True, header_style="bold")
    for column in ("file", "category", "conf", "status", "ms", "source"):
        table.add_column(column)
    for row in rows:
        confidence = f"{row.confidence:.3f}" if isinstance(row.confidence, float) else "—"
        table.add_row(row.file, row.category or "—", confidence, row.status,
                      f"{row.ms:.0f}", row.source or "—")
    out.print(table)


def _print_discover_report(report: DiscoverReport, naming_mode: str) -> None:
    out.print(f"{report.novel_count} novel file(s), {report.cluster_count} cluster(s) "
              f"({len(report.discovered)} usable, {report.small_clusters} singleton/small)")
    for name, why in report.embed_failures:
        err.print(f"[yellow]could not embed {name}: {why}[/yellow]")
    for found in report.discovered:
        out.print(f"\n[bold]{found.name}[/bold] — {found.description}")
        out.print(f"  files: {', '.join(found.files)}")
        if not found.used_llm and naming_mode != "manual":
            err.print("  [yellow]warning: naming LLM unreachable — used a fallback name.[/yellow]")
        if found.slug is not None:
            out.print(f"  [green]created '{found.slug}' (auto_created, review)[/green]")
        elif not found.created:
            err.print("  [red]not created (name clash or dry run)[/red]")


@app.command()
def status(config: Annotated[Optional[Path], typer.Option(help="config.toml")] = None) -> None:
    services = _services(config)
    cfg = services.cfg
    schema_row = services.conn.execute(
        "SELECT value FROM meta WHERE key='schema_version'"
    ).fetchone()
    schema_version = schema_row["value"] if schema_row else "?"
    out.print(f"[bold]root[/bold]       {cfg.paths.root}")
    out.print(f"[bold]inbox[/bold]      {cfg.paths.inbox}")
    out.print(f"[bold]organized[/bold] {cfg.paths.organized}")
    out.print(f"[bold]unsorted[/bold]   {cfg.paths.unsorted}")
    out.print(f"[bold]db[/bold]         {cfg.paths.db} (schema v{schema_version})")
    out.print(f"[bold]texts[/bold]      {cfg.paths.texts}")
    out.print(f"[bold]logs[/bold]       {cfg.paths.logs}")
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
    auto_discover: Annotated[bool, typer.Option("--auto-discover",
                                                help="run discover after ingest")] = False,
    config: Annotated[Optional[Path], typer.Option(help="config.toml")] = None,
) -> None:
    services = _services(config)
    services.cfg.ensure_dirs()
    active = services.categories.list_active()
    if not active:
        err.print("[yellow]no categories yet — files will be recorded as 'novel'.[/yellow]")
        err.print("[yellow]run `embly discover` to auto-create categories from them.[/yellow]")
    files = gather([path])
    if not files:
        err.print("[red]no files found[/red]")
        raise typer.Exit(1)
    err.print(f"{len(files)} file(s), {len(active)} category(ies)")
    results = services.ingester.ingest_many(files)
    _print_table(results)
    if auto_discover and any(r.status == "novel" for r in results):
        report = services.discoverer.discover()
        _print_discover_report(report, services.cfg.naming_llm.mode)


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


@app.command()
def discover(
    min_cluster_size: Annotated[int, typer.Option(help="minimum files per cluster")] = 2,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="show clusters without creating")] = False,
    config: Annotated[Optional[Path], typer.Option(help="config.toml")] = None,
) -> None:
    """Auto-create categories from novel files by clustering + LLM naming."""
    services = _services(config)
    report = services.discoverer.discover(min_cluster_size, dry_run)
    if report.novel_count == 0:
        err.print("[yellow]no novel files. ingest something first.[/yellow]")
        raise typer.Exit(1)
    _print_discover_report(report, services.cfg.naming_llm.mode)


@app.command()
def reclassify(
    status: Annotated[str, typer.Option(help="novel | review | all")] = "novel",
    config: Annotated[Optional[Path], typer.Option(help="config.toml")] = None,
) -> None:
    """Re-run classification on existing files with current categories."""
    if status not in ("novel", "review", "all"):
        err.print(f"[red]unknown status: {status} (novel | review | all)[/red]")
        raise typer.Exit(1)
    services = _services(config)
    active = services.categories.list_active()
    if not active:
        err.print("[red]no categories. add some first or run `embly discover`[/red]")
        raise typer.Exit(1)
    statuses = ["novel", "review", "classified"] if status == "all" else [status]
    rows = services.ingester.reclassify(statuses)
    if not rows:
        err.print("[yellow]no files to reclassify.[/yellow]")
        raise typer.Exit(0)
    err.print(f"reclassified {len(rows)} file(s) with {len(active)} categories")
    _print_table(rows)


@app.command()
def organize(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="show destinations without moving")] = False,
    status: Annotated[str, typer.Option(help="comma-separated statuses to organize")] = "classified,review",
    config: Annotated[Optional[Path], typer.Option(help="config.toml")] = None,
) -> None:
    """Move classified/review files into the organized tree."""
    services = _services(config)
    statuses = tuple(s.strip() for s in status.split(",") if s.strip())
    results = services.organizer.organize(statuses, dry_run=dry_run)
    if not results:
        err.print("[yellow]no files to organize (nothing with current_path IS NULL).[/yellow]")
        raise typer.Exit(0)
    table = Table(show_header=True, header_style="bold")
    for column in ("file", "category", "status", "moved_to"):
        table.add_column(column)
    for row in results:
        table.add_row(row.file, row.category or "—", row.status, row.moved_to or "—")
    out.print(table)


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
