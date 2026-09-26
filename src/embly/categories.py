from __future__ import annotations

import re
import sqlite3
import struct
from dataclasses import dataclass
from typing import Callable

import unidecode

from embly.db import now

Embedding = Callable[[str], list[float]]
ChangeHook = Callable[[str], None]
CacheClear = Callable[[], None]


@dataclass(frozen=True)
class Category:
    """The domain object the classifier and ingest speak in."""

    id: int
    name: str
    slug: str
    description: str
    status: str
    auto_created: bool
    centroid: bytes | None


@dataclass(frozen=True)
class CategoryCount:
    slug: str
    count: int


def slugify(name: str) -> str:
    normalized = unidecode.unidecode(name).lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return normalized or "misc"


def _row_to_category(row: sqlite3.Row) -> Category:
    return Category(
        id=row["id"],
        name=row["name"],
        slug=row["slug"],
        description=row["description"],
        status=row["status"],
        auto_created=bool(row["auto_created"]),
        centroid=row["centroid"],
    )


class CategoryService:
    """Category lifecycle.

    The five edit verbs hide slug derivation, centroid recomputation, embed-cache
    invalidation, and the post-edit change hook. The embedding function and the hook
    are injected, so this module is testable without laya and without a pipeline.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        embed: Embedding | None = None,
        clear_embed_cache: CacheClear | None = None,
        on_change: ChangeHook | None = None,
    ) -> None:
        self._conn = conn
        self._embed = embed
        self._clear_cache = clear_embed_cache
        self._on_change = on_change

    def add(self, name: str, description: str, *, auto_created: bool = False) -> Category:
        if not description.strip():
            raise ValueError("description is required (it drives classification accuracy)")
        slug = slugify(name)
        if self.get(slug) is not None:
            raise ValueError(f"category already exists: {slug}")
        ts = now()
        self._conn.execute(
            "INSERT INTO categories(name, slug, description, status, auto_created, centroid, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (name.strip(), slug, description.strip(), "active", 1 if auto_created else 0,
             self._centroid(name, description), ts, ts),
        )
        self._conn.commit()
        self._changed("all")
        return _row_to_category(self._require(slug))

    def describe(self, name: str, description: str) -> Category:
        if not description.strip():
            raise ValueError("description is required (it drives classification accuracy)")
        row = self._require(slugify(name))
        self._conn.execute(
            "UPDATE categories SET description=?, centroid=?, updated_at=? WHERE id=?",
            (description.strip(), self._centroid(row["name"], description), now(), row["id"]),
        )
        self._conn.commit()
        self._changed("all")
        return _row_to_category(self._require(row["slug"]))

    def rename(self, old: str, new: str, *, description: str | None = None) -> Category:
        row = self._require(slugify(old))
        new_slug = slugify(new)
        clash = self.get(new_slug)
        if clash is not None and clash.id != row["id"]:
            raise ValueError(f"category already exists: {new_slug}")
        desc = description if description is not None else row["description"]
        self._conn.execute(
            "UPDATE categories SET name=?, slug=?, description=?, centroid=?, updated_at=? WHERE id=?",
            (new.strip(), new_slug, desc, self._centroid(new, desc), now(), row["id"]),
        )
        self._conn.commit()
        self._changed("all")
        return _row_to_category(self._require(new_slug))

    def remove(self, name: str) -> None:
        row = self._require(slugify(name))
        self._conn.execute(
            "UPDATE categories SET status='removed', updated_at=? WHERE id=?", (now(), row["id"])
        )
        self._conn.execute(
            "UPDATE files SET category_id=NULL, status='review', updated_at=? WHERE category_id=?",
            (now(), row["id"]),
        )
        self._conn.commit()
        self._changed("all")

    def merge(self, source: str, target: str) -> Category:
        src = self._require(slugify(source))
        dst = self._require(slugify(target))
        if src["id"] == dst["id"]:
            raise ValueError("cannot merge a category into itself")
        self._conn.execute(
            "UPDATE files SET category_id=?, updated_at=? WHERE category_id=?", (dst["id"], now(), src["id"])
        )
        self._conn.execute(
            "UPDATE categories SET status='removed', updated_at=? WHERE id=?", (now(), src["id"])
        )
        self._conn.commit()
        self._changed("all")
        return _row_to_category(self._require(dst["slug"]))

    def assign_files(
        self,
        category_id: int,
        file_ids: list[int],
        *,
        status: str = "review",
        confidence: float | None = None,
        routing_model: str | None = None,
    ) -> None:
        """Assign files to a category (discover / reclassify path).

        The one seam for file→category mutations outside ingestion: keeps the
        update atomic and fires the change hook. The ``vec`` column stays
        pipeline-owned — callers update it separately when a file stays novel.
        """
        if not file_ids:
            return
        ts = now()
        self._conn.executemany(
            "UPDATE files SET category_id=?, status=?, confidence=?, routing_model=?, "
            "updated_at=? WHERE id=?",
            [(category_id, status, confidence, routing_model, ts, fid) for fid in file_ids],
        )
        self._conn.commit()
        self._changed("all")

    def list_active(self) -> list[Category]:
        return [
            _row_to_category(row)
            for row in self._conn.execute(
                "SELECT * FROM categories WHERE status='active' ORDER BY slug"
            )
        ]

    def get(self, name_or_slug: str) -> Category | None:
        slug = slugify(name_or_slug)
        row = self._conn.execute(
            "SELECT * FROM categories WHERE slug=? OR name=? LIMIT 1", (slug, name_or_slug.strip())
        ).fetchone()
        return _row_to_category(row) if row is not None else None

    def counts(self) -> list[CategoryCount]:
        rows = self._conn.execute(
            "SELECT c.slug, COUNT(f.id) AS n FROM categories c "
            "LEFT JOIN files f ON f.category_id=c.id WHERE c.status='active' GROUP BY c.slug ORDER BY c.slug"
        ).fetchall()
        return [CategoryCount(slug=row["slug"], count=row["n"]) for row in rows]

    def file_count(self, category_id: int) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM files WHERE category_id=?", (category_id,)
        ).fetchone()
        return row["n"]

    # -- internals -----------------------------------------------------------------

    def _require(self, slug: str) -> sqlite3.Row:
        row = self._conn.execute("SELECT * FROM categories WHERE slug=?", (slug,)).fetchone()
        if row is None:
            raise ValueError(f"unknown category: {slug}")
        return row

    def _centroid(self, name: str, description: str) -> bytes | None:
        if self._embed is None:
            return None
        vector = self._embed(f"{name.strip()} — {description.strip()}")
        return struct.pack(f"<{len(vector)}f", *vector)

    def _changed(self, scope: str) -> None:
        if self._clear_cache is not None:
            self._clear_cache()
        if self._on_change is not None:
            self._on_change(scope)
