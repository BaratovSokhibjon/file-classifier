# Component 1 — Watcher

> Source: `src/fileclassifier/watch.py`. Status: planning only.

## Responsibility

Turn file-system events in `inbox/` into durable, de-duplicated work items, and drive a
single worker loop that runs the pipeline.

## Behavior

- Uses `watchdog` to observe `inbox/` for create and move events.
- **Debounce / stability check:** a file is only queued once its size is stable across
  two polls one second apart, and it is at least 2 seconds old. This avoids processing
  half-written downloads.
- **Ignore patterns:** dotfiles, `*.part`, `*.tmp`, `*.crdownload`, Office lock files
  (`~$*`).
- Queue is **DB-backed**, not in-memory: `files WHERE status='pending'`. A daemon restart
  resumes exactly where it left off.
- Single worker loop processes one file at a time (extraction and inference are the
  expensive, mostly single-threaded steps).

## Modes

| Mode | Command | Use |
|---|---|---|
| Daemon | `fileclassifier watch` | Normal operation; watches `inbox/` |
| One-shot | `fileclassifier watch --once` | Drain everything pending, then exit |
| Backfill | `fileclassifier ingest PATH` | Ad-hoc file or folder; reuses the same pipeline |

`--once` and `ingest` are the test harness: they make the whole pipeline runnable from a
test with no background process.

## Interface

```python
def watch(inbox: Path, once: bool = False) -> None: ...
def enqueue(path: Path) -> int:      # returns new files.id, or existing id on dedupe
def drain() -> None:                 # process all pending rows
```

## Dependencies

- `watchdog`
- `db.py` (queue table + status transitions)
- `ingest.py` (the pipeline this loop invokes)
