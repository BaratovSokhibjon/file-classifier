# 01 — Overview

> Status: planning only.

## Goal

A personal, local platform that **auto-organizes files the moment they are uploaded**
(dropped into a watched folder). No predefined categories: the taxonomy emerges from
the files themselves, and the user manages it over time.

## Two core building blocks

1. **Universal OCR / text extraction** — pull usable text out of any file type:
   images and scanned PDFs (OCR), text-native documents (direct extraction), and
   audio/video (speech-to-text). Everything downstream operates on this text.
2. **The laya classifier** — a non-autoregressive *decision engine*. It answers typed
   questions (`choice`, `score`, `noul`) over text in a single forward pass, in 100+
   languages, via a `Router` that selects the right checkpoint per request. A `choice`
   question maps directly onto "which category does this file belong to?".

## Why laya (and its one limitation)

laya is a **pure decision engine — it cannot generate text**. It is excellent at
picking among *known* category labels, and it exposes a calibrated
`answer_confidence` for gating. Because it cannot invent a new category name, the
"category generation" requirement is split:

- **laya does the classification** among existing categories.
- **Embeddings do novelty detection** (does this file fit anything we know?).
- **A small local LLM (Ollama) does only the naming** of newly discovered clusters.

This separation keeps classification deterministic, fast, and hallucination-free,
while still allowing categories to emerge automatically.

## Decisions locked in

| Topic | Decision |
|---|---|
| Platform shape | CLI + watch-folder daemon (no web UI) |
| Input scope | Images + scanned PDFs, text-native files, audio/video |
| OCR engine | PaddleOCR (PP-OCRv5; `uz` / `ru` / `en` confirmed supported) |
| Taxonomy | Fully emergent and user-managed; no predefined categories |
| Category edits | Rename / add / remove / merge all trigger re-classification of affected files |
| Languages | Mixed / multilingual — laya `Router`, multilingual checkpoint as workhorse |
| Output | Move into `organized/<Category>/` + consistent renaming via a configurable template |
| New-category naming | Small local LLM (Ollama), used for naming only |
| Remove category | Its files fall back to `unsorted/`, then re-classify against remaining categories |

## One-line data flow

```
upload → extract text → embed + novelty check
       → laya classify (shortlist + confidence gate)
       → move + rename into organized/<Category>/
       → low confidence / unknown → review queue → corrections → tuning
```

See [02 — Architecture](02-architecture.md) for the full picture.
