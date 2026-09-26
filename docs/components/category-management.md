# Component 5 — Category Management

> Source: `src/fileclassifier/categories.py`. Status: planning only.

## Responsibility

Let the user add, rename, describe, remove, and merge categories — and treat every one of
those edits as a signal to **re-classify affected files** against the new structure.

This is the payoff of caching extracted text: re-classification replays text through
laya, never re-OCRs.

## Operations and triggers

| Command | Effect | Re-classification trigger |
|---|---|---|
| `categories add NAME --desc` | Create category, compute centroid | Sweep the `review` + `novel` queues against the new set (`--all` to re-run everything) |
| `categories rename OLD NEW` | Update name/slug/description, recompute centroid, clear embed cache | Re-classify `--all`; move the directory; re-render filenames containing `{category}` |
| `categories describe NAME --desc` | Edit the laya criteria text, recompute centroid | Re-classify `--all` (descriptions drive accuracy) |
| `categories remove OLD` | Deactivate category | Files → `unsorted/`, `status='review'`, then re-classify against remaining categories |
| `categories merge A B` | Bulk-assign A's files to B, deactivate A | Re-classify any leftovers, then recompute centroids |
| `categories list` / `show NAME` | Inspect name, slug, description, file count, `auto_created` | — |

## Re-classification engine

One function drives all triggers:

```python
def reclassify(scope, db, cfg) -> ReclassifyReport:
    # scope: all | category:<slug> | status:review | status:novel
    # 1. load cached text for the scoped files
    # 2. build ONE question schema from the current active category set
    # 3. router.predict_batch(requests, batch_size=32)   # mixed langs auto-group
    # 4. apply the same confidence gates as ingest
    # 5. move/flag results; append `decisions` rows with trigger='reclassify'
```

Properties:

- **Batch, not per-file.** `predict_batch` packs same-checkpoint requests into shared
  forward passes; a `rich` progress bar reports throughput.
- **Idempotent and resumable.** A job interrupted halfway leaves consistent per-file
  state; re-running is safe.
- **Audited.** Each re-run appends `decisions` rows tagged `reclassify`, so you can see
  how a rename changed outcomes.

## Removing a category (the chosen fallback)

Per the locked-in decision, removing a category does **not** auto-merge. Its files drop
back to `unsorted/` with `status='review'`, then immediately re-classify against the
remaining categories. Files that then fit a real category get filed; the rest stay in
review for a human.

## Renaming knock-on effects

Because the category slug is both a laya label and part of the output path and default
filename, `rename` fans out to:

1. the laya label + criteria (with centroid recompute),
2. the `organized/<slug>/` directory name,
3. every filename whose template includes `{category}`.

All three are handled by this component calling into
[Organizer & Naming](organizer-and-naming.md) after the re-classification pass.
