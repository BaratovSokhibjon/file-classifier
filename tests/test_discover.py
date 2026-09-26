from __future__ import annotations

from fakes import FakeDecisionEngine, FakeExtractor

from embly.categories import CategoryService
from embly.classify.naming_llm import NamingClient
from embly.config import ClassifyPolicy, NamingLlmPolicy, NoveltyPolicy, Paths
from embly.db import connect
from embly.discover import Discoverer
from embly.extract import Extraction
from embly.ingest import Ingester


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
    ingester = Ingester(conn, extractor, engine, service, paths, ClassifyPolicy())
    naming = NamingClient(NamingLlmPolicy(mode="manual"))
    discoverer = Discoverer(conn, engine, service, naming, NoveltyPolicy(), paths)
    return paths, conn, ingester, service, discoverer


def ingest_files(tmp_path, ingester, files: dict[str, str]):
    for name, content in files.items():
        path = tmp_path / name
        path.write_text(content)
        ingester.ingest(path)


def test_discover_backfills_embeddings_and_creates_categories(tmp_path):
    engine = FakeDecisionEngine(choice="x", confidence=0.2)
    extractor = FakeExtractor({
        name: Extraction(content, "text") for name, content in {
            "a.txt": "xx", "b.txt": "xxxx", "c.txt": "xxxxxxxxxxxx",
        }.items()
    })
    paths, conn, ingester, service, discoverer = build(tmp_path, engine, extractor)
    ingest_files(tmp_path, ingester, {"a.txt": "xx", "b.txt": "xxxx", "c.txt": "xxxxxxxxxxxx"})

    row = conn.execute("SELECT COUNT(*) n FROM files WHERE vec IS NOT NULL").fetchone()
    assert row["n"] == 0

    report = discoverer.discover(min_cluster_size=2)

    assert report.novel_count == 3
    assert len(report.discovered) == 1
    found = report.discovered[0]
    assert found.created and found.slug is not None
    assert not found.used_llm
    assert len(found.files) == 3
    row = conn.execute("SELECT COUNT(*) n FROM files WHERE vec IS NOT NULL").fetchone()
    assert row["n"] == 3
    rows = conn.execute("SELECT status FROM files").fetchall()
    assert all(r["status"] == "review" for r in rows)
    cats = service.list_active()
    assert len(cats) == 1 and cats[0].auto_created


def test_discover_dry_run_creates_nothing(tmp_path):
    engine = FakeDecisionEngine(choice="x", confidence=0.2)
    extractor = FakeExtractor({"a.txt": Extraction("xx", "text"), "b.txt": Extraction("xxxx", "text")})
    paths, conn, ingester, service, discoverer = build(tmp_path, engine, extractor)
    ingest_files(tmp_path, ingester, {"a.txt": "xx", "b.txt": "xxxx"})

    report = discoverer.discover(min_cluster_size=2, dry_run=True)

    assert len(report.discovered) == 1 and not report.discovered[0].created
    assert service.list_active() == []
    rows = conn.execute("SELECT status FROM files").fetchall()
    assert all(r["status"] == "novel" for r in rows)


def test_discover_reports_small_clusters(tmp_path):
    engine = FakeDecisionEngine(choice="x", confidence=0.2)
    extractor = FakeExtractor({"a.txt": Extraction("xx", "text")})
    paths, conn, ingester, service, discoverer = build(
        tmp_path, engine, extractor,
    )
    ingest_files(tmp_path, ingester, {"a.txt": "xx"})

    report = discoverer.discover(min_cluster_size=2)

    assert report.novel_count == 1
    assert report.discovered == [] and report.small_clusters == 1


def test_reclassify_assigns_to_new_categories(tmp_path):
    engine = FakeDecisionEngine(choice="books", confidence=0.9)
    extractor = FakeExtractor({"a.txt": Extraction("book text", "text")})
    paths, conn, ingester, service, discoverer = build(tmp_path, engine, extractor)
    ingest_files(tmp_path, ingester, {"a.txt": "book text"})
    assert conn.execute("SELECT status FROM files").fetchone()["status"] == "novel"

    service.add("books", "books and ebooks")
    results = ingester.reclassify(["novel"])

    assert len(results) == 1
    assert results[0].status == "classified" and results[0].category == "books"
    row = conn.execute("SELECT status, category_id FROM files").fetchone()
    assert row["status"] == "classified"
    decision = conn.execute("SELECT trigger FROM decisions").fetchone()
    assert decision["trigger"] == "reclassify"


def test_reclassify_skips_missing_cache(tmp_path):
    engine = FakeDecisionEngine(choice="x", confidence=0.9)
    extractor = FakeExtractor({"a.txt": Extraction("text", "text")})
    paths, conn, ingester, service, discoverer = build(
        tmp_path, engine, extractor, categories=[("x", "d")]
    )
    ingest_files(tmp_path, ingester, {"a.txt": "text"})
    import hashlib
    sha = hashlib.sha256(b"text").hexdigest()
    (paths.texts / f"{sha}.txt").unlink()

    results = ingester.reclassify(["classified"])

    assert len(results) == 1 and results[0].error == "no-cached-text"
