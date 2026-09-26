# Component 6 — Organizer & Naming

> Source: `src/fileclassifier/organize.py`. Status: planning only.

## Responsibility

Move each classified file into `organized/<Category>/` and rename it to a **consistent,
configurable** pattern. Works both at ingest time and retroactively (after a rename or
when the template changes).

## Move semantics

- Output path: `organized/<category-slug>/<rendered-name>.<ext>`.
- `shutil.move` (same-volume rename where possible, copy+delete across volumes).
- Provenance preserved: `original_name` and `original_path` stay in the DB; `current_path`
  is updated.
- **Dedupe:** if a target exists with a *different* sha256, append `-1`, `-2`, ...
  (or use the `{seq}` token). If the same sha256 already exists, the file is skipped as a
  duplicate (configurable to suffix-copy instead).

## Naming template

Config: `naming.template`, default `"{date}_{category}_{slug}"`.

| Token | Source | Fallback |
|---|---|---|
| `{date}` | Detected document date (regex over first ~2k chars: `YYYY-MM-DD`, `DD.MM.YYYY`, `DD/MM/YYYY`, `YYYY/MM/DD`) | File modified date |
| `{category}` | Category slug | — |
| `{slug}` | First meaningful line of extracted text, unidecode-transliterated, lowercased, ≤4 words, non-alphanumerics → `-` | Original filename stem |
| `{original}` | Original filename stem | — |
| `{seq}` | Collision counter | `0` |
| `{ext}` | Lowercased extension | — |

Example with the default template:

```
2026-09-26_invoice_acme-corp.pdf
2026-09-26_receipt_ubereats-order-4412.pdf
2026-09-26_contract_nda-brightsoft.pdf
```

Sanitization: strip control characters, collapse whitespace, cap total length (e.g. 120
chars for the rendered stem, preserving the extension).

## Doc-date detection

Cosmetic but useful. A small set of numeric date regexes is scanned over the head of the
text; the first plausible match wins. Month-name parsing in multiple languages is out of
scope for v1 — fall back to the file modified date.

## Retroactive rename

`fileclassifier rename-files [--all | --category X]` re-renders every affected filename
from the template. Used after:

- editing `naming.template`,
- `categories rename` (the `{category}` token changes).

Directory moves and filename re-renders are performed together so a renamed category is
fully consistent in one pass.

## Interface

```python
def render_name(tokens: dict, template: str) -> str: ...
def organize(file_row, category, cfg) -> Path: ...
def rename_all(scope, cfg) -> RenameReport: ...
def detect_doc_date(text: str) -> str | None: ...
def make_slug(text: str, max_words: int = 4) -> str: ...
```

## Edge cases

- **No extracted text:** `{slug}` falls back to the original stem; the file is usually in
  `review` anyway.
- **Same rendered name, different content:** sequence suffix.
- **Very long originals:** truncate the stem, keep the extension.
- **Hidden/underscore-prefixed categories:** disallowed at creation (would collide with
  the `.fc/` dot-directory convention).
