# Build Order

> Status: planning only. Each milestone is independently verifiable. Build them in order.

| # | Milestone | What it adds | Verification |
|---|---|---|---|
| **M0** | Scaffold | `pyproject.toml` (uv), config loader, DB + migration runner, typer skeleton, `status` | `uv run fileclassifier status` runs and prints paths, device, DB version |
| **M1** | Extraction layer | All extractors + registry, MIME sniffing, sha256 dedupe, text cache. **No ML.** | `ingest tests/fixtures/*` prints the extracted text head per file; uz/ru/en OCR fixture passes |
| **M2** | laya core | Router, question builder, shortlist, confidence gates, decision audit; `categories add` + `classify FILE` | Hand-add 3 categories, classify fixtures → choice + confidence + routing printed |
| **M3** | Novelty + emergence | Embeddings, centroids, clustering, Ollama naming, provisional categories; zero-category bootstrap | Fresh DB, drop 3 unknown-type docs → a provisional category is auto-created and files land in it, flagged review |
| **M4** | Watcher | `watchdog`, debounce/stability, DB-backed queue, resume, `--once` | Run daemon, copy fixtures into `inbox/` → organized tree appears |
| **M5** | Organizer + naming | Move semantics, template engine, collision seq, doc-date detection, `rename-files` | Names match template; `categories rename` moves the dir and re-renders names containing `{category}` |
| **M6** | Category management | All category commands + re-classify triggers + `predict_batch` with progress | rename / remove / merge flows re-file correctly; DB/audit shows cached text reused (no OCR re-run) |
| **M7** | Review loop | Review TUI + corrections table writes | Assign in the TUI → correction logged, file moved |
| **M8** | Accuracy tools | `tune` threshold suggestions + `finetune export` (laya `.jsonl`) | Threshold suggestion produced from corrections; jsonl validates against laya's dataset format |

## Critical first step

**Prove the PaddleOCR / `paddlepaddle` install on Apple Silicon before starting M1.**
It is the only dependency that could change the plan. If it fails, plug Surya in behind
the `extract/base.py` protocol — the rest of the pipeline is unaffected.

## Suggested sequencing rationale

- M1 before M2 because classification is meaningless without text, and the extraction
  layer can be fully tested with no models.
- M3 (emergence) is deliberately early: the product's defining requirement is
  zero-predefined categories, so the bootstrap path must work before polish.
- M4 before M5/M6 because watcher + ingest is the real end-to-end loop; naming and
  category management then operate on a working system.
- M7/M8 close the accuracy feedback loop and can be deferred if you just want it working.

## Phase 2 (after v1)

Fine-tune the multilingual checkpoint on exported corrections (laya's Kaggle 2×T4
notebook — free), then load the specialized checkpoint. This is where classification
accuracy makes its biggest jump.
