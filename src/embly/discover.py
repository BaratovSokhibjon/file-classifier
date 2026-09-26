from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from embly.categories import CategoryService
from embly.classify import DecisionEngine, NamingClient, bytes_to_vec, cluster_by_cosine, vec_to_bytes
from embly.classify.novelty import Cluster, NovelItem
from embly.config import NoveltyPolicy, Paths
from embly.db import now


@dataclass(frozen=True)
class DiscoveredCategory:
    name: str
    description: str
    files: list[str]
    used_llm: bool
    slug: str | None = None
    created: bool = False


@dataclass(frozen=True)
class DiscoverReport:
    novel_count: int
    cluster_count: int
    small_clusters: int
    discovered: list[DiscoveredCategory]
    embed_failures: list[tuple[str, str]]


class Discoverer:
    """The discovery module: novel files → embeddings → clusters → named categories.

    One interface — :meth:`discover` — hides embedding backfill, clustering,
    LLM naming (with fallback), category creation, and file assignment. The
    CLI and ``ingest --auto-discover`` are both thin adapters over this one
    interface, mirroring :class:`Ingester`. Dependencies are injected, so tests
    drive it with a fake engine and a manual-mode naming client.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        engine: DecisionEngine,
        categories: CategoryService,
        naming: NamingClient,
        policy: NoveltyPolicy,
        paths: Paths,
    ) -> None:
        self._conn = conn
        self._engine = engine
        self._categories = categories
        self._naming = naming
        self._policy = policy
        self._paths = paths

    def discover(self, min_cluster_size: int = 2, dry_run: bool = False) -> DiscoverReport:
        rows = self._conn.execute(
            "SELECT id, sha256, original_name, vec FROM files WHERE status='novel' ORDER BY id"
        ).fetchall()
        items, failures = self._load_items(rows)
        clusters = cluster_by_cosine(items, self._policy.cluster_cosine)
        big = [c for c in clusters if len(c.items) >= min_cluster_size]
        small = len(clusters) - len(big)

        discovered: list[DiscoveredCategory] = []
        for idx, cluster in enumerate(big):
            result = self._naming.name_cluster(self._excerpts(cluster), fallback_index=idx)
            files = [item.original_name for item in cluster.items]
            if dry_run:
                discovered.append(DiscoveredCategory(
                    name=result.name, description=result.description,
                    files=files, used_llm=result.used_llm,
                ))
                continue
            try:
                category = self._categories.add(
                    result.name, result.description, auto_created=True
                )
            except ValueError:
                discovered.append(DiscoveredCategory(
                    name=result.name, description=result.description,
                    files=files, used_llm=result.used_llm, created=False,
                ))
                continue
            self._categories.assign_files(
                category.id, [item.file_id for item in cluster.items], status="review"
            )
            discovered.append(DiscoveredCategory(
                name=result.name, description=result.description,
                files=files, used_llm=result.used_llm,
                slug=category.slug, created=True,
            ))
        return DiscoverReport(
            novel_count=len(rows), cluster_count=len(clusters),
            small_clusters=small, discovered=discovered, embed_failures=failures,
        )

    def _load_items(self, rows) -> tuple[list[NovelItem], list[tuple[str, str]]]:
        items: list[NovelItem] = []
        failures: list[tuple[str, str]] = []
        for row in rows:
            vec = row["vec"] if row["vec"] is not None else self._backfill_vec(row)
            if vec is None:
                failures.append((row["original_name"], self._failure_reason(row)))
                continue
            items.append(NovelItem(
                file_id=row["id"], sha=row["sha256"],
                original_name=row["original_name"], vec=bytes_to_vec(vec),
            ))
        return items, failures

    def _backfill_vec(self, row) -> bytes | None:
        """Compute and persist the embedding for a novel file ingested before
        embeddings existed (or whose embed failed at ingest)."""
        text_path = self._paths.texts / f"{row['sha256']}.txt"
        if not text_path.exists():
            return None
        try:
            vec = vec_to_bytes(self._engine.embed(text_path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            return None
        self._conn.execute(
            "UPDATE files SET vec=?, updated_at=? WHERE id=?", (vec, now(), row["id"])
        )
        self._conn.commit()
        return vec

    def _failure_reason(self, row) -> str:
        text_path = self._paths.texts / f"{row['sha256']}.txt"
        return "no-cached-text" if not text_path.exists() else "embed-failed"

    def _excerpts(self, cluster: Cluster) -> list[str]:
        excerpts: list[str] = []
        for item in cluster.items:
            text_path = self._paths.texts / f"{item.sha}.txt"
            if text_path.exists():
                excerpts.append(text_path.read_text(encoding="utf-8"))
        return excerpts
