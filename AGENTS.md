# AGENTS.md — embly

## Commands (uv-managed, Python >=3.12)

- `uv run pytest -q` — full suite (fast, ~0.1s, 32 tests, no models loaded)
- `uv run pytest tests/test_ingest.py -q` — single file; `-k <name>` for one test
- `uv run ruff check src tests` — lint (line-length 120, rules E,F,I,B)
- Format is black via pre-commit (`pre-commit run --all-files`); there is no CI workflow
- Probes (need real models/files): `.venv/bin/python scripts/try_laya.py samples/`, `.venv/bin/python scripts/try_ocr.py <image|pdf> [--classify]`
- `conftest.py` puts `src/` on `sys.path`, so tests import `embly` with no install step

## Architecture (see CONTEXT.md for domain terms)

Thin typer CLI (`src/embly/cli.py`, entry `embly = embly.cli:main`) over one pipeline:
`extract` → `classify` → `categories` → `ingest`, configured by grouped policies in `config.py`.
`Ingester.ingest_many` is the interface the future watcher will also use — keep it that way.
`docs/` is planning material and partly aspirational (mentions `watch.py`, `organize.py`,
`review.py`, `tune.py` — none exist yet). Trust `src/` over `docs/` on what is built.

## Seams — always inject fakes in tests (see `tests/fakes.py`)

Heavy deps are core (`paddleocr` for OCR) or optional extras (`office`, `media`, `llm` in `pyproject.toml`) and are
lazy-imported inside methods. Never instantiate the real ones in tests:

- `TextExtractor(ocr, engine=...)` — default engine is `PaddleEngine` (loads PaddleOCR per lang);
  pass `FakeOcrEngine` or a stub `extract()`
- `LayaEngine` implements the `DecisionEngine` protocol (`decide`/`embed`/`clear_cache`,
  downloads checkpoints on first use); pass `FakeDecisionEngine`
- `CategoryService(conn, embed=..., clear_embed_cache=..., on_change=...)` — pass a lambda embed
  or nothing (centroid then stays `None`)
- `Ingester(conn, extractor, engine, categories, paths, classify)` with `connect(tmp_path / "t.db")`

## Gotchas that will break things silently

- Config discovery: explicit `--config` > `./config.toml` > `~/.config/embly/config.toml` >
  defaults rooted at `~/Documents/embly`. Tests must build `Config` manually on `tmp_path`
  (see `test_ingest.py::make_config`) — never run the CLI/tests against the default root or you
  touch the user's real `~/Documents/embly` DB.
- Dedupe is by `sha256` and happens *before* extraction; duplicates return `status="duplicate"`
  without calling extractor or engine.
- Confidence gate (`ClassifyPolicy`: `assign_confidence=0.70`, `review_confidence=0.45`):
  `>= assign` → `classified`, `>= review` → `review`, else `novel`. With zero active categories
  the engine is never called and status is `novel`.
- Failed/empty extraction → `status="error"`, engine not called, no text cached, no decision row.
- Extracted text is cached at `.embly/texts/<sha256>.txt` only when non-blank; decisions append to
  `.embly/logs/decisions.jsonl` only when a category was chosen.
- `files.current_path` stays `NULL` until the (unbuilt) organizer moves it — don't assert otherwise.
- Category `slug` is the laya choice label and `description` is the laya criteria text:
  `add`/`describe` reject blank descriptions; `remove` parks member files to `review` with
  `category_id=NULL`; `merge` moves files then soft-removes the source.
- Extraction dispatch (`extract/base.py`): one owner per extension (overlap raises `RuntimeError`);
  extensionless files read as plain text; unknown suffix → `ok=False` (`unsupported(...)`); any
  handler exception becomes `Extraction("", "error:<Type>", ok=False)`, never raises.
- OCR strategy (`run_ocr`): tries each lang in `ocr.langs` order, early-exits on the first pass
  clearing `min_mean_confidence`, else keeps the best-scoring pass.
- `build_state` truncates body to `max_text_tokens * 4` chars; laya shortlist path kicks in only
  when `len(categories) > shortlist_threshold` (default 16).
