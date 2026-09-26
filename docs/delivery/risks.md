# Risks & Mitigations

> Status: planning only.

| Risk | Severity | Mitigation |
|---|---|---|
| **`paddlepaddle` wheel on Apple Silicon** — install may fail or be flaky on arm64 macOS | High | Prove it on day one of M1. If it fails, swap in Surya behind the `extract/base.py` protocol. This is the one dependency that could change the plan. |
| **laya multilingual ships without fitted calibration temperatures** and is over-confident as shipped | Medium | Treat thresholds as policy, not truth. Start conservative (0.70 / 0.45), log every decision, and let `tune` refine from corrections. |
| **Weak zero-shot accuracy** on niche document types (base checkpoints are near chance on typed-decision domains) | Medium | Good category descriptions, the review loop for corrections, threshold tuning, and eventually fine-tuning (documented 0.36 → 0.77 with laya's Kaggle notebook). |
| **Long documents** — accuracy varies beyond ~4,000 tokens even at `max_len=8192` | Low | Truncate to ~3,000 tokens for the choice question; `predict_long` available as a config escape hatch. Most documents of interest (invoices, receipts) are short. |
| **Whisper is slow on CPU** | Low | Default to the `small` model; offer `mlx-whisper` on Apple Silicon; audio is typically low-volume input. |
| **Ollama absent or not running** | Low | `naming.mode="manual"` fallback; startup check with a warning; novel clusters park in review and nothing blocks. |
| **Heavy install footprint** (`torch` ≈ 2 GB) | Low | `uv` + per-concern extras so OCR/media/office/LLM are opt-in; a native-text-only setup stays light. |
| **Category rename fan-out** could get out of sync (label, directory, filenames) | Medium | A single `reclassify` + `rename_all` pass handles all three in one command; operations are idempotent and audited. |
| **Duplicate uploads** waste work | Low | sha256 dedupe at ingest; `dedupe.on_duplicate` set to "skip" or "suffix". |
| **OCR language mis-detection** on mixed-script documents | Low | Ordered language passes with a confidence threshold and early exit; winning language recorded per file. |

## The two that actually matter

1. **PaddleOCR on Apple Silicon.** Resolve it first; it is the only external unknown.
2. **Classifier accuracy over time.** The platform is designed to improve itself through
   corrections. If the review loop and `tune`/`finetune` path are skipped, classification
   quality plateaus at laya's zero-shot level — which is not good enough for real
   document sets. Budget for Phase 2.
