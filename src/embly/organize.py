from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from embly.categories import CategoryService, slugify
from embly.config import NamingPolicy, Paths
from embly.db import now


@dataclass(frozen=True)
class OrganizeResult:
    file: str
    category: str | None
    moved_to: str | None
    status: str  # moved | already-organized | missing-source


class Organizer:
    """The organizer: moves ingested files into the organized tree.

    One interface — :meth:`organize` — hides the naming template, collision
    sequencing, and the unsorted parking lot. Sets ``files.current_path``;
    the CLI and the future watcher are thin adapters over it.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        categories: CategoryService,
        paths: Paths,
        naming: NamingPolicy,
    ) -> None:
        self._conn = conn
        self._categories = categories
        self._paths = paths
        self._naming = naming

    def organize(
        self,
        statuses: tuple[str, ...] = ("classified", "review"),
        dry_run: bool = False,
    ) -> list[OrganizeResult]:
        placeholders = ",".join("?" * len(statuses))
        rows = self._conn.execute(
            f"SELECT f.id, f.original_name, f.original_path, f.first_seen, "
            f"f.current_path, c.slug FROM files f "
            f"LEFT JOIN categories c ON f.category_id = c.id "
            f"WHERE f.current_path IS NULL AND f.status IN ({placeholders}) "
            f"ORDER BY f.id",
            statuses,
        ).fetchall()
        results: list[OrganizeResult] = []
        for row in rows:
            src = Path(row["original_path"])
            if not src.exists():
                results.append(OrganizeResult(
                    file=row["original_name"], category=row["slug"],
                    moved_to=None, status="missing-source",
                ))
                continue
            dest_dir = self._dest_dir(row["slug"])
            name = self._render_name(row, src)
            dest = self._unique(dest_dir, name)
            if not dry_run:
                dest_dir.mkdir(parents=True, exist_ok=True)
                src.rename(dest)
                self._conn.execute(
                    "UPDATE files SET current_path=?, updated_at=? WHERE id=?",
                    (str(dest), now(), row["id"]),
                )
                self._conn.commit()
            results.append(OrganizeResult(
                file=row["original_name"], category=row["slug"],
                moved_to=str(dest), status="moved",
            ))
        return results

    def _dest_dir(self, slug: str | None) -> Path:
        return self._paths.organized / slug if slug else self._paths.unsorted

    def _render_name(self, row, src: Path) -> str:
        stem = src.stem
        ext = src.suffix
        name = self._naming.template.format(
            date=row["first_seen"][:10],
            category=row["slug"] or "unsorted",
            slug=slugify(stem),
            original=stem,
            seq="01",
            ext=ext,
        )
        if ext and not name.endswith(ext):
            name += ext
        return name

    def _unique(self, dest_dir: Path, name: str) -> Path:
        candidate = dest_dir / name
        if not candidate.exists():
            return candidate
        stem = Path(name).stem
        ext = Path(name).suffix
        n = 1
        while True:
            candidate = dest_dir / f"{stem}_{n}{ext}"
            if not candidate.exists():
                return candidate
            n += 1
