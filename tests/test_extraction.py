from __future__ import annotations

from pathlib import Path

from fakes import FakeOcrEngine

from embly.config import OcrPolicy
from embly.extract import TextExtractor
from embly.extract.base import ExtractContext, Extraction, _dispatch_table, run_ocr


def test_dispatch_table_has_one_owner_per_extension():
    table = _dispatch_table()  # raises RuntimeError on any overlap
    assert table[".pdf"] is not None
    assert table[".txt"] is not None
    assert table[".html"] is not None


def test_plain_text_extracted(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("hello world")
    result = TextExtractor(OcrPolicy()).extract(path)
    assert result.ok and "hello world" in result.text and result.source == "text"


def test_extensionless_file_read_as_text(tmp_path):
    path = tmp_path / "Makefile"
    path.write_text("all:\n\techo hi")
    result = TextExtractor(OcrPolicy()).extract(path)
    assert result.ok and "echo hi" in result.text


def test_mime_overrides_unknown_suffix(tmp_path):
    path = tmp_path / "data.dat"
    path.write_text("plain")
    result = TextExtractor(OcrPolicy()).extract(path, mime="text/plain")
    assert result.ok and result.text == "plain"


def test_unsupported_returns_not_ok(tmp_path):
    path = tmp_path / "thing.bin"
    path.write_bytes(b"\x00\x01\x02")
    result = TextExtractor(OcrPolicy()).extract(path)
    assert not result.ok and result.source.startswith("unsupported")


def test_ocr_language_strategy_early_exits_on_confident_pass():
    engine = FakeOcrEngine({"uz": (["salom"], [0.95]), "ru": (["privet"], [0.10])})
    ctx = ExtractContext(ocr=OcrPolicy(langs=("uz", "ru", "en"), min_mean_confidence=0.8), engine=engine)
    result = run_ocr([Path("x.png")], ctx)
    assert result.text == "salom" and result.source.startswith("ocr:uz")
    assert ("x.png", "ru") not in engine.calls


def test_ocr_language_strategy_keeps_best_when_none_clear():
    engine = FakeOcrEngine({"uz": (["a"], [0.30]), "ru": (["b"], [0.60]), "en": (["c"], [0.10])})
    ctx = ExtractContext(ocr=OcrPolicy(langs=("uz", "ru", "en"), min_mean_confidence=0.9), engine=engine)
    result = run_ocr([Path("x.png")], ctx)
    assert result.text == "b" and result.source.startswith("ocr:ru")


def test_engine_failure_becomes_a_result_not_an_exception(tmp_path):
    class BoomEngine:
        def recognize(self, path, lang):
            raise RuntimeError("nope")

    path = tmp_path / "x.png"
    path.write_bytes(b"x")
    result = TextExtractor(OcrPolicy(langs=("en",)), engine=BoomEngine()).extract(path)
    assert not result.ok and result.source == "error:RuntimeError"


def test_extraction_dataclass_defaults_ok():
    assert Extraction("t", "src").ok is True
