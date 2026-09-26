from __future__ import annotations

import pytest

from embly.categories import CategoryService, slugify
from embly.db import connect

_FILE_SQL = (
    "INSERT INTO files(sha256, original_name, original_path, first_seen, text_extractor, "
    "status, category_id, created_at, updated_at) VALUES('s','n','p','t','text','classified',?, 't','t')"
)


def make_service(tmp_path, **kwargs) -> CategoryService:
    return CategoryService(connect(tmp_path / "t.db"), **kwargs)


def test_slugify_normalizes_and_falls_back():
    assert slugify("Medical Reports!") == "medical-reports"
    assert slugify("!!!") == "misc"


def test_add_computes_centroid_and_notifies(tmp_path):
    cleared: list[int] = []
    hooks: list[str] = []
    service = make_service(
        tmp_path,
        embed=lambda text: [1.0, 2.0],
        clear_embed_cache=lambda: cleared.append(1),
        on_change=hooks.append,
    )
    category = service.add("Invoices", "bills and faktura")
    assert category.slug == "invoices"
    assert category.centroid is not None
    assert cleared == [1]
    assert hooks == ["all"]


def test_add_without_embed_leaves_centroid_none(tmp_path):
    category = make_service(tmp_path).add("Travel", "tickets")
    assert category.centroid is None


def test_add_requires_description(tmp_path):
    with pytest.raises(ValueError):
        make_service(tmp_path).add("X", "   ")


def test_add_rejects_duplicate_slug(tmp_path):
    service = make_service(tmp_path)
    service.add("Invoices", "a")
    with pytest.raises(ValueError):
        service.add("invoices", "b")


def test_describe_updates_description_and_centroid(tmp_path):
    service = make_service(tmp_path, embed=lambda text: [float(len(text))])
    service.add("Invoices", "a")
    updated = service.describe("Invoices", "b")
    assert updated.description == "b"
    assert updated.centroid is not None


def test_rename_changes_slug_and_name(tmp_path):
    service = make_service(tmp_path)
    service.add("Invoices", "a")
    renamed = service.rename("Invoices", "Bills")
    assert renamed.slug == "bills" and renamed.name == "Bills"
    assert service.get("invoices") is None


def test_remove_parks_files_in_review(tmp_path):
    conn = connect(tmp_path / "t.db")
    service = CategoryService(conn)
    category = service.add("Travel", "tickets")
    conn.execute(_FILE_SQL, (category.id,))
    conn.commit()
    service.remove("Travel")
    row = conn.execute("SELECT status, category_id FROM files").fetchone()
    assert row["status"] == "review" and row["category_id"] is None
    assert service.get("travel").status == "removed"


def test_merge_reassigns_files_and_deactivates_source(tmp_path):
    conn = connect(tmp_path / "t.db")
    service = CategoryService(conn)
    source = service.add("A", "a")
    target = service.add("B", "b")
    conn.execute(_FILE_SQL, (source.id,))
    conn.commit()
    service.merge("A", "B")
    row = conn.execute("SELECT category_id FROM files").fetchone()
    assert row["category_id"] == target.id
    assert service.get("a").status == "removed"


def test_counts_only_active(tmp_path):
    conn = connect(tmp_path / "t.db")
    service = CategoryService(conn)
    category = service.add("Travel", "tickets")
    conn.execute(_FILE_SQL, (category.id,))
    conn.commit()
    assert service.counts()[0].count == 1
