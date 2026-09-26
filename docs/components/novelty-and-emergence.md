# Component 4 — Novelty & Emergence

> Sources: `src/embly/classify/novelty.py`, `src/embly/classify/naming_llm.py`.
> Status: planning only.

## Responsibility

Notice when a file fits nothing that exists, group such files into coherent new
categories, and give each new category a name. This is what makes the taxonomy
**emergent** rather than predefined.

laya cannot generate text, so this component is a three-stage mechanism:
embeddings detect novelty, clustering forms a candidate group, and a small local LLM
supplies the name. Classification itself stays entirely with laya.

## 1. Novelty detection

A file is a novelty candidate when **both** hold:

- `answer_confidence < review_confidence` (laya is unsure), and
- `max cosine(doc_vector, category_centroid) < novelty.cosine` (0.55).

If only confidence is low but the nearest centroid is still close, the file is merely
ambiguous → normal `review` queue. If the nearest centroid is far, it is genuinely new
material.

Embeddings are float32 mmBERT mean-pooled vectors; centroids are
`embed("<name> — <description>")` per category. The embed LRU cache is cleared whenever
categories change.

## 2. Clustering

Pending novel documents are grouped by pairwise cosine similarity with single-linkage
clustering at `novelty.cluster_cosine` (0.75). A lone document forms its own singleton
cluster — it still gets a category, so nothing is ever stuck without a home.

## 3. Naming (Ollama)

- Model: `qwen3:4b` (configurable), temperature 0, JSON mode.
- Input: excerpts from 2–3 documents in the cluster (first ~400 tokens each) plus top
  TF keywords.
- Output: `{"name": "...", "description": "..."}`.

Rules for `name`: 1–3 words, lowercase, hyphenated slug (becomes the laya label).
`description` becomes the laya criteria text and is immediately useful for future
classification.

The resulting category is created with `auto_created = 1, status = 'active'`. Its files
are filed into it and flagged `review` so the user can confirm or rename.

## Isolation and fallback

The LLM is deliberately boxed in: it **only ever names and describes clusters**. It never
classifies, never sees the pipeline's decisions, and is never on the critical path.

- `naming.mode = "llm" | "manual"` (config).
- Startup does an `ollama list` check; if Ollama is unreachable, the system degrades to
  `manual` and warns. In manual mode, novel clusters park in `review` for the user to
  name, so the pipeline never blocks.

## Bootstrap: the zero-category path

At a fresh database there are no categories and no centroids. Every first file is a
novelty candidate by construction. The first few files therefore flow:

```
file → no centroids → novel → cluster → Ollama names it → first category
```

After a handful of files, real categories exist and the normal path takes over.

## Interface

```python
def is_novel(doc_vec, centroids, confidence, cfg) -> bool: ...
def pending_clusters(db, cfg) -> list[list[int]]:            # file ids
def name_cluster(cluster, cfg) -> tuple[str, str]:           # (name, description)
def create_category_from_cluster(db, cluster, name, desc) -> int: ...
```
