# CLI Reference

> Source: `src/fileclassifier/cli.py` (typer). Status: planning only.

Entry point: `fileclassifier` (a short alias can be added later).

## Daily use

```
fileclassifier watch [--inbox PATH] [--once]   # daemon, or drain-once
fileclassifier status                           # counts, model/device, ollama state
fileclassifier review                           # interactive TUI over review + novel
```

## Ingest

```
fileclassifier ingest PATH                      # a file or a folder (recursive)
fileclassifier classify FILE                    # debug: print choice, confidence, routing
```

`classify` is a read-only diagnostic — it runs the pipeline in memory and prints the full
answer, without moving the file.

## Categories

```
fileclassifier categories list
fileclassifier categories show NAME
fileclassifier categories add NAME --desc "criteria text"
fileclassifier categories describe NAME --desc "criteria text"
fileclassifier categories rename OLD NEW
fileclassifier categories remove NAME
fileclassifier categories merge A B
```

Every mutating category command triggers re-classification of the affected scope
(see [Category Management](components/category-management.md)).

## Re-processing

```
fileclassifier reclassify [--all | --category X | --status review | --status novel]
fileclassifier rename-files [--all | --category X]
```

## Accuracy

```
fileclassifier tune                             # confidence histogram vs corrections
                                                # → suggested thresholds
fileclassifier finetune export [--out data.jsonl]
```

## Global flags

| Flag | Effect |
|---|---|
| `--config PATH` | Use a specific `config.toml` |
| `--db PATH` | Override the SQLite database location |
| `--device cuda\|mps\|cpu` | Force the laya device |
| `--verbose` / `-v` | Debug logging to stderr |
| `--json` | Machine-readable output where applicable (e.g. `status`) |
