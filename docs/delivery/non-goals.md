# Non-Goals (v1)

> Status: planning only. Explicitly out of scope for the first version, with a note on how
> each could be added later.

| Out of scope | Why | Later path |
|---|---|---|
| **Nested / hierarchical categories** | Flat `organized/<Category>/` is simpler and laya handles flat choices well | Two-level coarse→fine questions (laya's documented hierarchical remedy), or a `parent_id` on categories |
| **Archive extraction** (zip, rar, 7z) | Not selected as an input scope | Add an `extract/archive.py` that unpacks to a temp dir and re-queues inner files |
| **Cloud OCR APIs** | Chosen engine is local PaddleOCR; privacy and cost | Add behind the `Extractor` protocol as a per-file option |
| **Multi-user / server mode** | CLI + watch folder was the chosen shape | `laya[serve]` exposes a Jev-compatible HTTP API; add auth + a shared DB then |
| **Web UI** | CLI only | The pipeline is already service-shaped; a thin FastAPI layer could sit in front |
| **Full-text search over extracted text** | Not required to organize files | SQLite FTS5 over `.fc/texts/` is a cheap, isolated add-on |
| **Content-based dedupe beyond exact sha256** | Exact-hash dedupe covers the common case | Perceptual hashing (images) / near-duplicate text embeddings |
| **Month-name / multilingual date parsing** | Cosmetic; numeric dates cover most documents | Extend `detect_doc_date` with locale-aware parsing |
| **PII detection / redaction** | Not requested; laya supports `noul` questions + redaction hooks if wanted | Add a `noul` question and a `on_predict_start` redaction hook |
| **Automatic fine-tuning** | Training needs a GPU and careful validation | Keep it manual: `finetune export` → laya's Kaggle notebook → drop in the checkpoint |
