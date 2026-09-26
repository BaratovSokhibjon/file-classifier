# CLI Reference

> Source: `src/embly/cli.py` (typer). Status: planning only.

Entry point: `embly` (a short alias can be added later).

## Daily use

```
embly watch [--inbox PATH] [--once]   # daemon, or drain-once
embly status                           # counts, model/device, ollama state
embly review                           # interactive TUI over review + novel
```

## Ingest

```
embly ingest PATH                      # a file or a folder (recursive)
embly classify FILE                    # debug: print choice, confidence, routing
```

`classify` is a read-only diagnostic — it runs the pipeline in memory and prints the full
answer, without moving the file.

## Categories

```
embly categories list
embly categories show NAME
embly categories add NAME --desc "criteria text"
embly categories describe NAME --desc "criteria text"
embly categories rename OLD NEW
embly categories remove NAME
embly categories merge A B
```

Every mutating category command triggers re-classification of the affected scope
(see [Category Management](components/category-management.md)).

## Re-processing

```
embly reclassify [--all | --category X | --status review | --status novel]
embly rename-files [--all | --category X]
```

## Accuracy

```
embly tune                             # confidence histogram vs corrections
                                                # → suggested thresholds
embly finetune export [--out data.jsonl]
```

## Global flags

| Flag | Effect |
|---|---|
| `--config PATH` | Use a specific `config.toml` |
| `--db PATH` | Override the SQLite database location |
| `--device cuda\|mps\|cpu` | Force the laya device |
| `--verbose` / `-v` | Debug logging to stderr |
| `--json` | Machine-readable output where applicable (e.g. `status`) |
