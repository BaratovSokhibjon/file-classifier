# embly

A local watch-folder daemon that auto-organizes files on upload. Drop a file into
`inbox/`; it is text-extracted (OCR / native / transcription), classified by
[laya](https://github.com/NandhaKishorM/laya) into an emergent, user-managed taxonomy,
renamed consistently, and moved into `organized/<Category>/`.

No predefined categories — categories are discovered from the files and managed by you.

> **Status:** planning. Nothing is built yet. See [`docs/`](docs/) for the full plan.

## Plan

Start at [`docs/README.md`](docs/README.md).

Quick links:

- [Overview](docs/01-overview.md) — goal and locked-in decisions
- [Architecture](docs/02-architecture.md) — pipeline and runtime layout
- [Data Model](docs/03-data-model.md) — SQLite schema
- [Components](docs/components/README.md) — watcher, extraction, classification, novelty, categories, organizer, review
- [CLI](docs/reference/cli.md) · [Config](docs/reference/config.md) · [Dependencies](docs/reference/dependencies.md)
- [Build Order](docs/delivery/build-order.md) · [Risks](docs/delivery/risks.md) · [Non-Goals](docs/delivery/non-goals.md)

## First step

Prove the PaddleOCR / `paddlepaddle` install on Apple Silicon before writing any other
code — it is the only dependency that could change the plan.
