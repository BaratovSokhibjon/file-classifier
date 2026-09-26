# embly — domain model

A local watch-folder daemon. Files dropped into `inbox/` are turned into text, classified
into an emergent, user-managed taxonomy, and filed into `organized/<Category>/`.

## Concepts

- **File** — one document tracked by the system, keyed by `sha256`. Its extracted text is
  cached at `.embly/texts/<sha256>.txt`; the database stores provenance, not text.
- **Category** — a named bucket with a stable `slug` (the laya choice label) and a
  `description` (the laya criteria text). Categories are emergent: they are created from
  the files, not predefined. A category carries a **centroid**, the embedding of
  `"<name> — <description>"`.
- **Decision** — the answer to "which category does this file belong to?", with an
  `answer_confidence`. Gated: `>= assign_confidence` files directly, `review_confidence`
  to `assign_confidence` files and flags `review`, below that is a **novelty** candidate.
- **Ingestion** — the pipeline that turns a path into a filed file: dedupe, extraction,
  text caching, classification, the confidence gate, and persistence.
- **Extraction** — turning any file into text (native text, OCR, Office conversion,
  speech-to-text). Produces an `Extraction` (text, source label, ok flag).
- **Novelty** — noticing a file fits nothing known. At ingest, a low-confidence file
  whose embedding is still close to a category centroid (`novelty.cosine`) parks in
  `review`; a truly novel file keeps its vector for **discovery** — clustering the
  pending novel files (`novelty.cluster_cosine`) and naming each cluster (LLM or
  fallback) into a provisional `auto_created` category.
- **Organizer / Naming** — moving a file into the organized tree and rendering its name
  from a template. Not yet built.
- **Review** — the queue of `review` and `novel` files a human corrects; corrections
  become ground truth.

## Modules (the seams)

- **`extract`** (`TextExtractor`) — the extraction module. Interface: `extract(path, mime)
  -> Extraction`. Hides the dispatch table, extension sets, OCR language strategy, and
  graceful degradation. The OCR engine sits behind the **`OcrEngine`** seam
  (`PaddleEngine` in production, a fake in tests).
- **`classify`** (`LayaEngine`) — the classifier. Interface: `decide(state, categories) ->
  Decision`, plus `embed` and `clear_cache`. The `DecisionEngine` seam isolates laya.
- **`categories`** (`CategoryService`) — the category lifecycle. Interface: `add`,
  `describe`, `rename`, `remove`, `merge`, `assign_files` (plus `list_active`, `get`,
  `counts`). Hides slug derivation, centroid recomputation, embed-cache invalidation,
  and the change hook.
- **`ingest`** (`Ingester`) — the ingestion pipeline. Interface: `ingest(path)` /
  `ingest_many(paths) -> [IngestResult]`, plus `reclassify(statuses)`. The CLI and the
  (future) watcher are thin adapters over these interfaces.
- **`discover`** (`Discoverer`) — the discovery module. Interface:
  `discover(min_cluster_size, dry_run) -> DiscoverReport`. Hides embedding backfill,
  clustering, LLM naming (with fallback), category creation, and file assignment.
- **`config`** — grouped policy objects (`Paths`, `OcrPolicy`, `ClassifyPolicy`,
  `NamingPolicy`, `NoveltyPolicy`) inside one `Config`; each module receives only the
  policy it uses.
