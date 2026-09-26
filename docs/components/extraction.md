# Component 2 — Extraction (Universal Text Layer)

> Source: `src/embly/extract/`. Status: planning only.

## Responsibility

Given any file, produce text. Native-text formats are read directly; image-like content
goes through OCR; audio/video goes through speech-to-text. "Universal OCR" is really a
universal **text extraction** layer — OCR is only used where there is no text layer.

## Dispatch table

| Input | Tool | Notes |
|---|---|---|
| jpg / png / bmp / tiff / webp / heic | `pillow` (+`pillow-heif`) → PaddleOCR | PP-OCRv5 recognition, server model |
| pdf | `PyMuPDF` | If text layer < ~100 chars/page → scanned → rasterize at 300 dpi → PaddleOCR |
| docx / xlsx / pptx / html / eml / csv / json | `markitdown` | One dependency for all Office-ish formats; cap spreadsheet cells |
| txt / md / code | `charset-normalizer` + read | Encoding-tolerant |
| mp3 / wav / m4a / ogg / flac / mov / mp4 | `ffmpeg` → Whisper | Extract 16 kHz mono audio, then transcribe |
| unknown / binary | — | Park in `unsorted/`, `status='error'`, surface in review |

## OCR language strategy

PaddleOCR PP-OCRv5 supports 106 languages, confirmed to include the ones that matter
here: `uz` (Uzbek), `ru` (Russian), `en` (English).

Config: `ocr.langs = ["uz", "ru", "en"]`, `ocr.min_mean_confidence = 0.80`.

Algorithm:
1. Run the `uz` pass.
2. If mean recognition confidence < threshold, retry with `ru`, then `en`.
3. Early-exit on the first pass that clears the threshold.

The winning language is recorded on the file row (`text_extractor`), useful for
debugging and for tuning OCR later.

## Rasterization limits

- PDF OCR is capped at 50 pages (configurable) to bound worst-case time. Native-text
  PDFs are not capped — PyMuPDF reads them cheaply.
- Converted images are kept in memory only; no intermediate files.

## Swap seam

The extraction module exposes one interface in `extract/base.py`:

```python
class TextExtractor:
    def __init__(self, ocr: OcrPolicy, engine: OcrEngine | None = None) -> None: ...
    def extract(self, path: Path, mime: str | None = None) -> Extraction: ...
```

A dispatch table (extension → handler) picks the right extractor. The `OcrEngine` protocol
is the injected seam: production uses `PaddleEngine`, tests pass a fake. This means the OCR
engine can be replaced (e.g. Surya) without touching the pipeline — the primary insurance
against the PaddleOCR-on-Apple-Silicon install risk.

## Graceful degradation

- Missing `ffmpeg` → media extraction reports "disabled" once at startup; audio/video
  files park in review instead of crashing the worker.
- Missing optional extras (`[media]`, `[office]`) → the corresponding extractor
  is simply unavailable, with a clear message. (OCR ships by default.)

## Output

A single string plus a label for which extractor ran. Text is written to
`.embly/texts/<sha256>.txt`; only the path and extractor name go in the DB.
