# Component 7 — Review Loop

> Source: `src/embly/review.py`. Status: planning only.

## Responsibility

Handle everything the classifier was not confident about, and turn each human decision
into ground truth that improves the system.

Review is the one inherently interactive part of a CLI tool, so it is implemented as a
terminal UI (`rich` + `prompt-toolkit`) rather than a web page.

## What appears in the queue

- `status='review'` — assigned below the confidence bar, or parked in `unsorted/` after a
  category removal, or extractor yielded no text.
- `status='novel'` — a singleton/cluster still waiting for a name (only possible in
  `naming.mode="manual"`, or when Ollama is unreachable).

## Per-file view

For each file the TUI shows:

- original filename and current extracted-text excerpt,
- the current category (if any) and its `answer_confidence`,
- the top-3 shortlist labels with probabilities (from the decision audit),
- routing model used.

## Actions

| Key | Action | Writes |
|---|---|---|
| `a` | Assign to a category (pick from list, or create a new one inline) | `corrections` row; file → `classified`; move+rename |
| `c` | Create a new category and assign | `categories` row + `corrections` row |
| `s` | Skip for now | — |
| `t` | Show full extracted text | — |
| `d` | Drop the row from review (leave file where it is) | status update only |

## Corrections as ground truth

Every assign/create writes a `corrections` row (`source='review'`). These serve two
purposes:

1. **Threshold tuning** — `embly tune` compares corrected outcomes against the
   confidence each file received, and suggests new `assign_confidence` /
   `review_confidence` values for the coverage/accuracy trade-off you want.
2. **Fine-tuning dataset** — `embly finetune export` turns corrections (plus
   confident decisions, optionally) into a laya-format `.jsonl` so the checkpoint can be
   specialized on your documents later. See [Build Order](../delivery/build-order.md) M8.

## Why this matters

laya's base checkpoints are near chance zero-shot on niche typed-decision domains, and
accuracy jumps sharply after fine-tuning on domain data (a documented 0.36 → 0.77
pattern). The review loop is how this platform accumulates that data from day one, at
almost no extra cost — the user is already fixing the few files that need attention.

## Interface

```python
def review_queue(db) -> list[FileRow]: ...
def run_tui(db, cfg) -> None: ...             # main loop
def apply_correction(db, file_id, category_id, source) -> None: ...
```
