# Dependencies

> Status: planning only. Python 3.12 (laya requires ≥ 3.10). Managed with `uv`.

## Core (always installed)

| Package | Purpose |
|---|---|
| `laya` | The classifier / decision engine |
| `typer` | CLI framework |
| `rich` | Progress bars, tables, output |
| `prompt-toolkit` | Interactive review TUI |
| `watchdog` | Inbox file-system observer |
| `pymupdf` | PDF text extraction + rasterization |
| `pillow` | Image handling |
| `pillow-heif` | HEIC/HEIF decoding (iPhone photos) |
| `charset-normalizer` | Text-file encoding detection |
| `numpy` | Embedding math, centroids, clustering |
| `unidecode` | Transliteration for filename slugs |
| `puremagic` | MIME sniffing (pure-Python, avoids libmagic) |

## Optional extras

| Extra | Packages | Enables |
|---|---|---|
| `[ocr]` | `paddleocr`, `paddlepaddle` | OCR for images and scanned PDFs |
| `[office]` | `markitdown` | docx / xlsx / pptx / html / eml / csv |
| `[media]` | `faster-whisper` | audio/video transcription (`ffmpeg` via brew) |
| `[llm]` | `ollama` | Naming of new categories |
| `[fast]` | `laya[fast]` | Optional TileLang GPU fast path |

Install examples:

```bash
uv sync --extra ocr --extra office --extra media --extra llm
# or minimal, native-text only:
uv sync
```

## External binaries

| Binary | Needed for | Install |
|---|---|---|
| `ffmpeg` | Audio/video extraction | `brew install ffmpeg` |
| Ollama server | Category naming | `brew install ollama` (or the app) |

## Models (downloaded on first use)

| Model | Size / notes | Used by |
|---|---|---|
| `convaiinnovations/laya` (english) | ModernBERT-large, 421M | Router for English text |
| `convaiinnovations/laya` (multilingual) | mmBERT-base, 322M; also the embedder | Router + embeddings |
| PP-OCRv5 detection + recognition | PaddleOCR; `uz`/`ru`/`en` | OCR |
| Whisper `small` | via faster-whisper | Media |
| `qwen3:4b` | via Ollama | New-category naming only |

## Why laya extras matter

laya ships optional installs for serving (`laya[serve]`), ONNX (`laya[onnx]`), MCP
(`laya[mcp]`), and LangChain (`laya[langchain]`). None are required here — this project
embeds laya as a library. If the platform is ever moved behind an API or into a
multi-user service, `laya[serve]` and `laya[onnx]` are the natural next steps.

## Footprint warning

`torch` (pulled by laya) is on the order of 2 GB. The extras are deliberately separable
so a native-text-only deployment installs far less.
