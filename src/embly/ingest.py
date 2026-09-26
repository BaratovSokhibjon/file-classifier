from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from embly.categories import CategoryService
from embly.classify import DecisionEngine, build_state
from embly.config import ClassifyPolicy, Paths
from embly.db import now as _now
from embly.extract import TextExtractor


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

    Dedupe, extraction, text caching, classification, the confidence gate, and
    persistence all live here. The CLI and the watcher are both thin adapters over this
    one interface. Dependencies are injected, so tests drive it with a fake extractor,
    a fake decision engine, and a temp database.
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
        clock: Callable[[], str] = _now,
    ) -> None:
        self._conn = conn
        self._extractor = extractor
        self._engine = engine
        self._categories = categories
        self._paths = paths
        self._classify = classify
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
        shortlist_json: str | None = None
        error = None if extraction.ok else extraction.source

        if extraction.text.strip():
            self._paths.texts.mkdir(parents=True, exist_ok=True)
            (self._paths.texts / f"{sha}.txt").write_text(extraction.text, encoding="utf-8")

            active = self._categories.list_active()
            if active:
                state = build_state(path.name, extraction.text, self._classify.max_text_tokens)
                decision = self._engine.decide(state, active)
                category, confidence, model, ms, shortlist_json = (
                    decision.choice, decision.confidence, decision.model, decision.ms,
                    decision.shortlist_json,
                )
                if confidence >= self._classify.assign_confidence:
                    status = "classified"
                elif confidence >= self._classify.review_confidence:
                    status = "review"
                else:
                    status = "novel"
            else:
                status = "novel"

        category_row = self._categories.get(category) if category else None
        cursor = self._conn.execute(
            "INSERT INTO files(sha256, original_name, original_path, current_path, ext, size, "
            "first_seen, text_extractor, status, category_id, confidence, routing_model, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sha, path.name, str(path.resolve()), None, path.suffix.lower(),
             path.stat().st_size, ts, extraction.source, status,
             category_row.id if category_row else None,
             confidence, model, ts, ts),
        )
        if category_row is not None:
            self._conn.execute(
                "INSERT INTO decisions(file_id, category_id, confidence, shortlist_json, "
                "routing_model, trigger, created_at) VALUES(?,?,?,?,?,?,?)",
                (cursor.lastrowid, category_row.id, confidence, shortlist_json, model, "ingest", ts),
            )
        self._conn.commit()
        self._append_decision_log(ts, sha, category, confidence, model, shortlist_json)
        return IngestResult(file=path.name, sha=sha, category=category, confidence=confidence,
                            status=status, source=extraction.source, ms=ms, error=error)

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
