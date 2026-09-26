# 02 — Architecture

> Status: planning only.

## Pipeline

```
inbox/  ──watchdog──▶  debounced event
   │
   ▼
Dispatch (mime + magic sniff)
   ├── image (jpg/png/tiff/webp/heic) ──▶ PaddleOCR (PP-OCRv5)
   ├── pdf ──▶ PyMuPDF: has text layer? ──yes──▶ extract text
   │                                  └─no──▶ rasterize 300dpi ─▶ PaddleOCR
   ├── docx/xlsx/pptx/html/eml/csv ────▶ markitdown
   ├── txt/md/code ───────────────────▶ charset-normalizer + read
   └── audio/video ─▶ ffmpeg ─▶ 16k mono wav ─▶ Whisper
   │
   ▼
SQLite: file row (sha256, text cached to .embly/texts/<sha>.txt)
   │
   ▼
Embed (laya embed_fn, mmBERT mean-pool) ─▶ novelty check vs category centroids
   ├── known ─▶ shortlist top-k categories ─▶ laya Router choice question ─▶ confidence gate
   │             ├─ ≥0.70     ─▶ assign ─▶ move + rename (template)
   │             └─ 0.45–0.70 ─▶ assign + flag `review`
   └── novel ─▶ cluster with pending novel docs ─▶ Ollama names cluster (provisional category)
                 ─▶ files land in it, flagged `auto_created` + `review`
   │
   ▼
CLI review loop ─▶ user corrections ─▶ decisions/corrections audit ─▶ re-classify + fine-tune set
```

## Why this shape

- **Text is cached once.** Re-classification after a category edit never re-runs OCR —
  it replays cached text through laya. Category edits are cheap and common by design.
- **Embeddings serve two jobs** with one model: shortlisting candidate labels for laya,
  and detecting novelty against category centroids.
- **The LLM is boxed in.** Ollama only ever receives excerpts to produce a name and a
  one-line description. It never classifies and is optional (`naming.mode = "manual"`).
- **Confidence is policy, not truth.** Thresholds are configurable and re-derived from
  measured corrections via `embly tune`.

## Runtime directory layout

```
~/Documents/embly/          # root, configurable
├── inbox/                           # watched drop folder
├── organized/<Category>/            # sorted output tree
├── unsorted/                        # low-confidence / removed-category parking
└── .embly/
    ├── embly.db                # SQLite (WAL)
    ├── texts/<sha256>.txt           # cached extracted text
    └── logs/decisions.jsonl         # append-only decision audit
```

## Source layout

```
embly/
├── pyproject.toml            # uv-managed, Python 3.12; OCR in core, extras: [media] [llm] [office]
├── config.toml.example
├── docs/                     # this documentation
├── src/embly/
│   ├── cli.py                # typer app: all commands
│   ├── config.py             # tomllib + defaults
│   ├── db.py                 # sqlite3 stdlib, WAL, tiny migration runner
│   ├── watch.py              # watchdog observer + debounce + worker loop
│   ├── ingest.py             # pipeline orchestrator
│   ├── extract/
│   │   ├── base.py           # Extractor protocol + registry  ← swap seam for OCR engine
│   │   ├── images.py         # pillow (+pillow-heif) → PaddleOCR
│   │   ├── pdf.py            # pymupdf text-or-rasterize
│   │   ├── office.py         # markitdown
│   │   ├── media.py          # ffmpeg + whisper
│   │   └── plain.py          # charset-normalizer
│   ├── classify/
│   │   ├── laya_core.py      # Router, question builder, shortlist, gates
│   │   ├── novelty.py        # embed, centroids, clustering
│   │   └── naming_llm.py     # ollama client, isolated + optional
│   ├── categories.py         # CRUD + reclassify triggers
│   ├── organize.py           # move + naming-template engine + collision seq
│   ├── review.py             # interactive TUI (rich + prompt-toolkit)
│   └── tune.py               # threshold analysis from audit
└── tests/                    # fixtures: one tiny file per type incl. uz/ru/en
```

The `extract/base.py` protocol exists so the OCR engine can be swapped (e.g. to Surya)
without touching the rest of the pipeline. This is the main insurance against the
PaddleOCR-on-Apple-Silicon install risk — see [Risks](../delivery/risks.md).
