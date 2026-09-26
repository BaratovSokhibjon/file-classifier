from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from embly.categories import Category, CategoryService
from embly.classify import (
    DecisionEngine,
    build_state,
    bytes_to_vec,
    centroid_to_vec,
    cosine_similarity,
    vec_to_bytes,
)
from embly.config import ClassifyPolicy, NoveltyPolicy, Paths
from embly.db import now as _now
from embly.extract import TextExtractor

_DEFAULT_NOVELTY = NoveltyPolicy()


@dataclass(frozen=True)
class IngestResult:
    file: str
    sha: str
    category: str | None
    confidence: float | None
    status: str
    source: str
    ms: float
    error: str | None = None


class Ingester:
    """The ingestion pipeline.

    Dedupe, extraction, text caching, classification, the confidence gate, the
    centroid novelty check, and persistence all live here. The CLI and the
    watcher are both thin adapters over this one interface. Dependencies are
    injected, so tests drive it with a fake extractor, a fake decision engine,
    and a temp database.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        extractor: TextExtractor,
        engine: DecisionEngine,
        categories: CategoryService,
        paths: Paths,
        classify: ClassifyPolicy,
        *,
        novelty: NoveltyPolicy = _DEFAULT_NOVELTY,
        clock: Callable[[], str] = _now,
    ) -> None:
        self._conn = conn
        self._extractor = extractor
        self._engine = engine
        self._categories = categories
        self._paths = paths
        self._classify = classify
        self._novelty = novelty
        self._clock = clock

    def ingest_many(self, paths: list[Path]) -> list[IngestResult]:
        return [self.ingest(path) for path in paths]

    def ingest(self, path: Path) -> IngestResult:
        sha = _sha256(path)
        if self._conn.execute("SELECT id FROM files WHERE sha256=?", (sha,)).fetchone():
            return IngestResult(file=path.name, sha=sha, category=None, confidence=None,
                                status="duplicate", source="—", ms=0.0)

        extraction = self._extractor.extract(path)
        ts = self._clock()
        status: str = "error"
        category: str | None = None
        confidence: float | None = None
        model: str | None = None
        ms = 0.0
        vec_bytes: bytes | None = None
        error = None if extraction.ok else extraction.source

        if extraction.text.strip():
            self._paths.texts.mkdir(parents=True, exist_ok=True)
            (self._paths.texts / f"{sha}.txt").write_text(extraction.text, encoding="utf-8")

            active = self._categories.list_active()
            if active:
                state = build_state(path.name, extraction.text, self._classify.max_text_tokens)
                decision = self._engine.decide(state, active)
                category, confidence, model, ms = (
                    decision.choice, decision.confidence, decision.model, decision.ms,
                )
                status, vec_bytes = self._gate(decision.confidence, extraction.text, active)
            else:
                status = "novel"

        category_row = self._categories.get(category) if category else None
        cursor = self._conn.execute(
            "INSERT INTO files(sha256, original_name, original_path, current_path, ext, size, "
            "first_seen, text_extractor, status, category_id, confidence, routing_model, vec, "
            "created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sha, path.name, str(path.resolve()), None, path.suffix.lower(),
             path.stat().st_size, ts, extraction.source, status,
             category_row.id if category_row else None,
             confidence, model, vec_bytes, ts, ts),
        )
        if category_row is not None:
            self._record_decision(cursor.lastrowid, category_row.id, decision, "ingest", ts, sha)
        self._conn.commit()
        return IngestResult(file=path.name, sha=sha, category=category, confidence=confidence,
                            status=status, source=extraction.source, ms=ms, error=error)

    def reclassify(self, statuses: list[str]) -> list[IngestResult]:
        """Re-run classification on existing files using current categories.

        Reads cached text from ``.embly/texts/<sha>.txt`` — never re-extracts.
        """
        active = self._categories.list_active()
        if not active:
            return []
        placeholders = ",".join("?" * len(statuses))
        rows = self._conn.execute(
            f"SELECT id, sha256, original_name, status FROM files "
            f"WHERE status IN ({placeholders}) ORDER BY id",
            statuses,
        ).fetchall()
        results: list[IngestResult] = []
        for row in rows:
            text_path = self._paths.texts / f"{row['sha256']}.txt"
            if not text_path.exists():
                results.append(IngestResult(
                    file=row["original_name"], sha=row["sha256"], category=None,
                    confidence=None, status=row["status"], source="no-cached-text",
                    ms=0.0, error="no-cached-text",
                ))
                continue
            text = text_path.read_text(encoding="utf-8")
            state = build_state(row["original_name"], text, self._classify.max_text_tokens)
            decision = self._engine.decide(state, active)
            ts = self._clock()
            new_status, vec_bytes = self._gate(decision.confidence, text, active)
            cat_row = self._categories.get(decision.choice) if decision.choice else None
            if cat_row is not None:
                self._categories.assign_files(
                    cat_row.id, [row["id"]], status=new_status,
                    confidence=decision.confidence, routing_model=decision.model,
                )
            else:
                self._conn.execute(
                    "UPDATE files SET status='novel', category_id=NULL, confidence=?, "
                    "routing_model=?, updated_at=? WHERE id=?",
                    (decision.confidence, decision.model, ts, row["id"]),
                )
            self._conn.execute("UPDATE files SET vec=? WHERE id=?", (vec_bytes, row["id"]))
            if cat_row is not None:
                self._record_decision(row["id"], cat_row.id, decision, "reclassify", ts,
                                      row["sha256"])
            self._conn.commit()
            results.append(IngestResult(
                file=row["original_name"], sha=row["sha256"], category=decision.choice,
                confidence=decision.confidence, status=new_status, source="reclassify",
                ms=decision.ms,
            ))
        return results

    def _gate(self, confidence: float, text: str, active: list[Category]) -> tuple[str, bytes | None]:
        """The one confidence gate: high → classified, mid → review, low → the
        centroid novelty check. Similar-to-something parks in ``review``; truly
        novel keeps its vector for ``discover`` to cluster on."""
        if confidence >= self._classify.assign_confidence:
            return "classified", None
        if confidence >= self._classify.review_confidence:
            return "review", None
        vec = self._embed_or_none(text)
        if vec is not None and self._max_centroid_similarity(vec, active) >= self._novelty.cosine:
            return "review", None
        return "novel", vec

    def _embed_or_none(self, text: str) -> bytes | None:
        try:
            return vec_to_bytes(self._engine.embed(text))
        except Exception:  # noqa: BLE001
            return None

    def _max_centroid_similarity(self, vec: bytes, active: list[Category]) -> float:
        arr = bytes_to_vec(vec)
        best = 0.0
        for cat in active:
            if cat.centroid is None:
                continue
            best = max(best, cosine_similarity(arr, centroid_to_vec(cat.centroid)))
        return best

    def _record_decision(
        self, file_id: int, category_id: int, decision, trigger: str, ts: str, sha: str,
    ) -> None:
        self._conn.execute(
            "INSERT INTO decisions(file_id, category_id, confidence, shortlist_json, "
            "routing_model, trigger, created_at) VALUES(?,?,?,?,?,?,?)",
            (file_id, category_id, decision.confidence, decision.shortlist_json,
             decision.model, trigger, ts),
        )
        self._append_decision_log(ts, sha, decision.choice, decision.confidence,
                                  decision.model, decision.shortlist_json)

    def _append_decision_log(
        self, ts: str, sha: str, category: str | None, confidence: float | None,
        model: str | None, shortlist_json: str | None,
    ) -> None:
        if category is None:
            return
        self._paths.logs.mkdir(parents=True, exist_ok=True)
        entry = json.dumps({
            "ts": ts, "sha": sha, "category": category, "confidence": confidence,
            "model": model, "shortlist": shortlist_json,
        })
        with (self._paths.logs / "decisions.jsonl").open("a", encoding="utf-8") as f:
            f.write(entry + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
