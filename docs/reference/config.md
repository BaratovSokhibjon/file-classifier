# Configuration Reference

> Source: `src/embly/config.py`. Status: planning only.
> File: `config.toml` (repo-local) or `~/.config/embly/config.toml`.
> Precedence: CLI flag > env var > config file > built-in default.

```toml
[paths]
inbox = "~/Documents/embly/inbox"
root  = "~/Documents/embly"

[naming]
template = "{date}_{category}_{slug}"
# tokens: {date} {category} {slug} {original} {seq} {ext}

[ocr]
engine = "paddle"                 # swap seam for a future "surya"
langs  = ["uz", "ru", "en"]       # tried in order
min_mean_confidence = 0.80        # retry next language below this
max_pdf_ocr_pages   = 50
rasterize_dpi       = 300

[classify]
shortlist_k       = 12            # engage shortlist when categories exceed 16
assign_confidence = 0.70          # >= : assign directly
review_confidence = 0.45          # <  : novelty candidate
max_text_tokens   = 3000          # truncation budget for the choice question
batch_size        = 32            # re-classification batch size

[novelty]
cosine         = 0.55             # max centroid similarity below which a file is novel
cluster_cosine = 0.75             # single-linkage clustering threshold

[naming_llm]
mode  = "llm"                     # "manual" = no LLM anywhere
model = "qwen3:4b"                # any Ollama model
host  = "http://127.0.0.1:11434"

[media]
whisper_model = "small"           # or an mlx-whisper model on Apple Silicon
ffmpeg        = "ffmpeg"

[dedupe]
on_duplicate = "skip"             # "skip" | "suffix"
```

## Notes

- **Thresholds are policy.** The defaults are starting points; `embly tune`
  derives better values from your corrections. See [Classification](components/classification.md).
- **`ocr.engine`** is the documented swap seam: the pipeline depends on the `Extractor`
  protocol, not on PaddleOCR directly.
- **Environment variables** mirror the important keys for agents/servers (e.g.
  `LAYA_DEVICE`, plus `FILECLASSIFIER_CONFIG`); reserved but not required for v1.
- **`naming_llm.host`** points at a local Ollama server. If it is unreachable at startup,
  the system switches to `manual` naming and warns.
