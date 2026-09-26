from __future__ import annotations

from fakes import FakeDecisionEngine, FakeExtractor

from embly.categories import CategoryService
from embly.config import ClassifyPolicy, Config, NamingPolicy, NoveltyPolicy, OcrPolicy, Paths
from embly.db import connect
from embly.extract import Extraction
from embly.ingest import Ingester


def make_config(tmp_path, novelty_overrides=None, **classify_overrides) -> Config:
    root = tmp_path / "fc"
    paths = Paths(
        root=root,
        inbox=root / "inbox",
        organized=root / "organized",
        unsorted=root / "unsorted",
        db=root / ".embly/embly.db",
        texts=root / ".embly/texts",
        logs=root / ".embly/logs",
    )
    return Config(
        paths=paths,
        ocr=OcrPolicy(),
        classify=ClassifyPolicy(**classify_overrides),
        naming=NamingPolicy(),
        novelty=NoveltyPolicy(**(novelty_overrides or {})),
    )


def build(tmp_path, engine, extractor, *, categories=(), novelty_overrides=None,
          **classify_overrides):
    cfg = make_config(tmp_path, novelty_overrides=novelty_overrides, **classify_overrides)
    conn = connect(cfg.paths.db)
    service = CategoryService(conn, embed=engine.embed)
    for name, description in categories:
        service.add(name, description)
    ingester = Ingester(conn, extractor, engine, service, cfg.paths, cfg.classify,
                        novelty=cfg.novelty)
    return cfg, conn, ingester, service


def test_ingest_classifies_and_caches_text(tmp_path):
    engine = FakeDecisionEngine(choice="invoice", confidence=0.9)
    extractor = FakeExtractor({"a.txt": Extraction("hello invoice", "text")})
    cfg, conn, ingester, _ = build(tmp_path, engine, extractor, categories=[("invoice", "bills")])
    path = tmp_path / "a.txt"
    path.write_text("hello invoice")

    result = ingester.ingest(path)

    assert result.status == "classified" and result.category == "invoice"
    assert engine.calls == 1
    assert (cfg.paths.texts / f"{result.sha}.txt").read_text() == "hello invoice"
    decision = conn.execute("SELECT trigger FROM decisions").fetchone()
    assert decision["trigger"] == "ingest"


def test_duplicate_is_not_reprocessed(tmp_path):
    engine = FakeDecisionEngine()
    extractor = FakeExtractor({"a.txt": Extraction("x", "text")})
    _, conn, ingester, _ = build(tmp_path, engine, extractor, categories=[("invoice", "bills")])
    path = tmp_path / "a.txt"
    path.write_text("x")

    first = ingester.ingest(path)
    second = ingester.ingest(path)

    assert first.status == "classified" and second.status == "duplicate"
    assert conn.execute("SELECT COUNT(*) n FROM files").fetchone()["n"] == 1
    assert engine.calls == 1


def test_low_confidence_flags_review(tmp_path):
    engine = FakeDecisionEngine(choice="invoice", confidence=0.5)
    extractor = FakeExtractor({"a.txt": Extraction("text", "text")})
    _, _, ingester, _ = build(tmp_path, engine, extractor, categories=[("invoice", "bills")])
    path = tmp_path / "a.txt"
    path.write_text("text")
    assert ingester.ingest(path).status == "review"


def test_very_low_confidence_flags_novel_when_dissimilar(tmp_path):
    engine = FakeDecisionEngine(choice="invoice", confidence=0.2)
    extractor = FakeExtractor({"a.txt": Extraction("text", "text")})
    _, _, ingester, _ = build(
        tmp_path, engine, extractor,
        categories=[("invoice", "bills")],
        novelty_overrides={"cosine": 0.99},
    )
    path = tmp_path / "a.txt"
    path.write_text("text")
    assert ingester.ingest(path).status == "novel"


def test_centroid_similarity_flips_novel_to_review(tmp_path):
    engine = FakeDecisionEngine(choice="invoice", confidence=0.2)
    extractor = FakeExtractor({"a.txt": Extraction("text", "text")})
    _, conn, ingester, _ = build(
        tmp_path, engine, extractor,
        categories=[("invoice", "bills")],
        novelty_overrides={"cosine": 0.55},
    )
    path = tmp_path / "a.txt"
    path.write_text("text")
    result = ingester.ingest(path)
    assert result.status == "review"
    row = conn.execute("SELECT vec FROM files").fetchone()
    assert row["vec"] is None


def test_novel_file_keeps_vec_for_discover(tmp_path):
    engine = FakeDecisionEngine(choice="invoice", confidence=0.2)
    extractor = FakeExtractor({"a.txt": Extraction("text", "text")})
    _, conn, ingester, _ = build(
        tmp_path, engine, extractor,
        categories=[("invoice", "bills")],
        novelty_overrides={"cosine": 0.99},
    )
    path = tmp_path / "a.txt"
    path.write_text("text")
    result = ingester.ingest(path)
    assert result.status == "novel"
    row = conn.execute("SELECT vec FROM files").fetchone()
    assert row["vec"] is not None


def test_classified_file_gets_no_embedding(tmp_path):
    engine = FakeDecisionEngine(choice="invoice", confidence=0.9)
    extractor = FakeExtractor({"a.txt": Extraction("hello invoice", "text")})
    _, conn, ingester, _ = build(tmp_path, engine, extractor, categories=[("invoice", "bills")])
    path = tmp_path / "a.txt"
    path.write_text("hello invoice")
    embeds_before = engine.embed_calls  # category centroid creation already embeds once

    ingester.ingest(path)

    assert engine.embed_calls == embeds_before
    row = conn.execute("SELECT vec FROM files").fetchone()
    assert row["vec"] is None


def test_no_categories_means_novel_without_classifying(tmp_path):
    engine = FakeDecisionEngine()
    extractor = FakeExtractor({"a.txt": Extraction("text", "text")})
    _, conn, ingester, _ = build(tmp_path, engine, extractor)
    path = tmp_path / "a.txt"
    path.write_text("text")
    result = ingester.ingest(path)
    assert result.status == "novel" and engine.calls == 0 and engine.embed_calls == 0
    row = conn.execute("SELECT vec FROM files").fetchone()
    assert row["vec"] is None


def test_failed_extraction_records_error(tmp_path):
    engine = FakeDecisionEngine()
    extractor = FakeExtractor({"a.bin": Extraction("", "error:RuntimeError", ok=False)})
    _, conn, ingester, _ = build(tmp_path, engine, extractor)
    path = tmp_path / "a.bin"
    path.write_bytes(b"\x00")
    result = ingester.ingest(path)
    assert result.status == "error" and result.error == "error:RuntimeError"
    assert engine.calls == 0
    assert conn.execute("SELECT status FROM files").fetchone()["status"] == "error"


def test_text_body_is_truncated_to_budget(tmp_path):
    engine = FakeDecisionEngine(confidence=0.9)
    extractor = FakeExtractor({"a.txt": Extraction("x" * 500, "text")})
    _, _, ingester, _ = build(
        tmp_path, engine, extractor,
        categories=[("invoice", "bills")],
        max_text_tokens=10,
    )
    path = tmp_path / "a.txt"
    path.write_text("x" * 500)

    ingester.ingest(path)

    assert engine.last_state is not None and len(engine.last_state["body"]) == 40


def test_current_path_is_null_until_organized(tmp_path):
    engine = FakeDecisionEngine(choice="invoice", confidence=0.9)
    extractor = FakeExtractor({"a.txt": Extraction("hello", "text")})
    _, conn, ingester, _ = build(tmp_path, engine, extractor, categories=[("invoice", "bills")])
    path = tmp_path / "a.txt"
    path.write_text("hello")

    ingester.ingest(path)

    row = conn.execute("SELECT current_path FROM files").fetchone()
    assert row["current_path"] is None


def test_decision_log_is_appended(tmp_path):
    engine = FakeDecisionEngine(choice="invoice", confidence=0.9)
    extractor = FakeExtractor({"a.txt": Extraction("hello", "text")})
    cfg, _, ingester, _ = build(tmp_path, engine, extractor, categories=[("invoice", "bills")])
    path = tmp_path / "a.txt"
    path.write_text("hello")

    ingester.ingest(path)

    log = (cfg.paths.logs / "decisions.jsonl").read_text().strip()
    assert "invoice" in log and "0.9" in log
