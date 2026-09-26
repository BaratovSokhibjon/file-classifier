# Component 3 — Classification (laya core)

> Source: `src/embly/classify/laya_core.py`. Status: planning only.

## Responsibility

Ask laya "which category?" over the extracted text, with the right checkpoint, the right
label set size, and a confidence verdict.

## Setup

```python
import laya

router = laya.Router(default="multilingual", preload=["english", "multilingual"])
agent  = laya.load("convaiinnovations/laya", subfolder="multilingual")
embed  = laya.cached_embed_fn(laya.embed_fn_from_agent(agent))   # LRU 4096
```

- `default="multilingual"` because traffic is mixed / non-English and very short Latin
  text often carries no language signal.
- Both automatic checkpoints are preloaded so a language flip costs detection only.
- The multilingual encoder doubles as the embedding model for shortlist + novelty
  (one model, one cache).

## Building the question

```python
def questions_for(shortlist):
    return {"category": {
        "type": "choice",
        "instructions": "Which category does this document belong to?",
        "criteria": {c.slug: c.description for c in shortlist},   # k <= 12
    }}
```

- `state` = `{"subject": original_filename, "body": text_truncated_to_budget}`.
- **Criteria quality matters most.** laya classifies partly by reading the label
  descriptions, so every category needs a real `description`. Descriptions are seeded by
  the naming LLM on creation and are user-editable (`categories describe`).

## Handling many categories

laya accuracy degrades past roughly 20 options because options share the
`head_max_len` token budget. Two remedies are baked in:

| Category count | Path |
|---|---|
| ≤ 16 | `router.predict(state, questions_for(all), max_len=8192)` |
| > 16 | `laya.predict_shortlist(agent, state, questions_for(all), embed_fn=embed, k=12)` |

`predict_shortlist` embeds the state and the labels, narrows to the top-k labels, then
runs a single forward pass over those k. The reported probability is over the shortlist.
This scales to hundreds of categories; the only hard ceiling (>~126 options on `laya`,
>~254 on multilingual) is never approached.

## Long documents

- Truncate to `classify.max_text_tokens = 3000` tokens for the choice question
  (invoices/receipts are short; contracts rarely need more to be categorizable).
- If longer context is genuinely needed, `agent.predict_long(state, questions)` windows
  the state and aggregates. Kept as a config escape hatch, not the default.

## Confidence gating

Gate on **`answer_confidence`** (the probability of the reported answer), not raw
`confidence` (1 − normalised entropy).

| `answer_confidence` | Action |
|---|---|
| ≥ `assign_confidence` (0.70) | Assign directly |
| `review_confidence`–`assign_confidence` (0.45–0.70) | Assign, flag `status='review'` |
| < `review_confidence` (0.45) | Hand to the [novelty pipeline](novelty-and-emergence.md) |

Thresholds are **policy, derived from your data** — start conservative and let
`embly tune` refine them. Note: `laya-multilingual` ships without fitted
calibration temperatures and is over-confident as shipped, so the numbers are best
treated as a ranking signal initially.

## Audit

Every decision is appended to `decisions` and to `.embly/logs/decisions.jsonl` via a laya
`on_predict_end` hook: routing model, elapsed ms, full answer distribution, shortlist.
This is the raw material for `tune`.

## Label hygiene

- Labels are lowercase-hyphen slugs.
- Never use boolean-like labels (`true`/`false`, `yes`/`no`) — a documented laya trap.

## Batching (re-classification)

Re-classification after a category edit uses
`router.predict_batch(requests, batch_size=32)`. Mixed-language files auto-group by
checkpoint, and results are restored to input order. Text comes from the cache — OCR is
never re-run.
