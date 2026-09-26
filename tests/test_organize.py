from __future__ import annotations

from pathlib import Path

from fakes import FakeDecisionEngine, FakeExtractor

from embly.categories import CategoryService
from embly.config import ClassifyPolicy, NamingPolicy, NoveltyPolicy, Paths
from embly.db import connect
from embly.extract import Extraction
from embly.ingest import Ingester
from embly.organize import Organizer


def make_paths(tmp_path) -> Paths:
    root = tmp_path / "fc"
    return Paths(
        root=root, inbox=root / "inbox", organized=root / "organized",
        unsorted=root / "unsorted", db=root / ".embly/embly.db",
        texts=root / ".embly/texts", logs=root / ".embly/logs",
    )


def build(tmp_path, engine, extractor, *, categories=()):
    paths = make_paths(tmp_path)
    conn = connect(paths.db)
    service = CategoryService(conn, embed=engine.embed)
    for name, description in categories:
        service.add(name, description)
    ingester = Ingester(conn, extractor, engine, service, paths, ClassifyPolicy(),
                        novelty=NoveltyPolicy(cosine=0.99))
    organizer = Organizer(conn, service, paths, NamingPolicy())
    return paths, conn, ingester, service, organizer


def test_organize_moves_classified_file(tmp_path):
    engine = FakeDecisionEngine(choice="books", confidence=0.9)
    extractor = FakeExtractor({"a.txt": Extraction("hello book", "text")})
    paths, conn, ingester, service, organizer = build(
        tmp_path, engine, extractor, categories=[("books", "books and ebooks")]
    )
    src = tmp_path / "a.txt"
    src.write_text("hello book")
    ingester.ingest(src)

    results = organizer.organize(("classified",))

    assert len(results) == 1 and results[0].status == "moved"
    assert not src.exists()
    dest = Path(results[0].moved_to)
    assert dest.exists() and dest.parent == paths.organized / "books"
    assert dest.suffix == ".txt"
    row = conn.execute("SELECT current_path FROM files").fetchone()
    assert row["current_path"] == str(dest)


def test_organize_collision_appends_suffix(tmp_path):
    engine = FakeDecisionEngine(choice="books", confidence=0.9)
    extractor = FakeExtractor({
        "a.txt": Extraction("hello book one", "text"),
    })
    paths, conn, ingester, service, organizer = build(
        tmp_path, engine, extractor, categories=[("books", "books and ebooks")]
    )
    d1 = tmp_path / "dir1"
    d2 = tmp_path / "dir2"
    d1.mkdir()
    d2.mkdir()
    src1 = d1 / "a.txt"
    src2 = d2 / "a.txt"
    src1.write_text("hello book one")
    src2.write_text("hello book two")
    extractor.mapping["a.txt"] = Extraction("hello book", "text")
    ingester.ingest(src1)
    ingester.ingest(src2)

    results = organizer.organize(("classified",))

    assert len(results) == 2
    dests = {Path(r.moved_to).name for r in results}
    assert len(dests) == 2
    assert any("_1" in name for name in dests)


def test_organize_dry_run_does_not_move(tmp_path):
    engine = FakeDecisionEngine(choice="books", confidence=0.9)
    extractor = FakeExtractor({"a.txt": Extraction("hello book", "text")})
    paths, conn, ingester, service, organizer = build(
        tmp_path, engine, extractor, categories=[("books", "books and ebooks")]
    )
    src = tmp_path / "a.txt"
    src.write_text("hello book")
    ingester.ingest(src)

    results = organizer.organize(("classified",), dry_run=True)

    assert len(results) == 1 and results[0].status == "moved"
    assert src.exists()
    row = conn.execute("SELECT current_path FROM files").fetchone()
    assert row["current_path"] is None


def test_organize_missing_source_skips(tmp_path):
    engine = FakeDecisionEngine(choice="books", confidence=0.9)
    extractor = FakeExtractor({"a.txt": Extraction("hello book", "text")})
    paths, conn, ingester, service, organizer = build(
        tmp_path, engine, extractor, categories=[("books", "books and ebooks")]
    )
    src = tmp_path / "a.txt"
    src.write_text("hello book")
    ingester.ingest(src)
    src.unlink()

    results = organizer.organize(("classified",))

    assert len(results) == 1 and results[0].status == "missing-source"


def test_organize_no_category_goes_to_unsorted(tmp_path):
    engine = FakeDecisionEngine(choice="x", confidence=0.2)
    extractor = FakeExtractor({"a.txt": Extraction("text", "text")})
    paths, conn, ingester, service, organizer = build(tmp_path, engine, extractor)
    src = tmp_path / "a.txt"
    src.write_text("text")
    ingester.ingest(src)
    assert conn.execute("SELECT status FROM files").fetchone()["status"] == "novel"

    results = organizer.organize(("novel",))

    assert len(results) == 1 and results[0].status == "moved"
    dest = Path(results[0].moved_to)
    assert dest.parent == paths.unsorted


def test_organize_skips_already_organized(tmp_path):
    engine = FakeDecisionEngine(choice="books", confidence=0.9)
    extractor = FakeExtractor({"a.txt": Extraction("hello book", "text")})
    paths, conn, ingester, service, organizer = build(
        tmp_path, engine, extractor, categories=[("books", "books and ebooks")]
    )
    src = tmp_path / "a.txt"
    src.write_text("hello book")
    ingester.ingest(src)
    organizer.organize(("classified",))

    again = organizer.organize(("classified",))

    assert again == []
