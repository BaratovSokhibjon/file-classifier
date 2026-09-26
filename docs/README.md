# embly — Documentation

Build plan for a local watch-folder daemon that auto-organizes files. Files dropped
into `inbox/` are text-extracted (OCR / native text / transcription), classified by
[laya](https://github.com/NandhaKishorM/laya) into an **emergent, user-managed
taxonomy**, renamed via a configurable template, and moved into `organized/<Category>/`.

> **Status:** planning only. Nothing is built yet. This folder is the specification.

## Start here

- [01 — Overview](01-overview.md) — goal, constraints, the decisions that were made
- [02 — Architecture](02-architecture.md) — the pipeline and runtime layout
- [03 — Data Model](03-data-model.md) — SQLite schema and how text/vectors are stored

## Components

The pipeline, in order:

1. [Watcher](components/watcher.md) — observes `inbox/`, debounces, queues work
2. [Extraction](components/extraction.md) — universal text layer (OCR, PDF, Office, media)
3. [Classification](components/classification.md) — laya Router, shortlist, confidence gates
4. [Novelty & Emergence](components/novelty-and-emergence.md) — new categories get created
5. [Category Management](components/category-management.md) — user edits trigger re-classification
6. [Organizer & Naming](components/organizer-and-naming.md) — move + rename template
7. [Review Loop](components/review-loop.md) — corrections feed tuning and fine-tuning

## Reference

- [CLI](reference/cli.md) — every command
- [Configuration](reference/config.md) — `config.toml`
- [Dependencies](reference/dependencies.md) — packages and install extras

## Delivery

- [Build Order](delivery/build-order.md) — milestones, each independently verifiable
- [Risks](delivery/risks.md) — what could go wrong and the mitigation
- [Non-Goals](delivery/non-goals.md) — deliberately out of scope for v1
