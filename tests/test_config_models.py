from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from typer.testing import CliRunner

from embly.classify.laya_core import LayaEngine
from embly.cli import app
from embly.config import (
    ClassifyPolicy,
    MediaPolicy,
    OcrPolicy,
    format_value,
    get_dotted,
    load_config,
    load_raw,
    parse_value,
    save_raw,
    set_dotted_raw,
)
from embly.extract import TextExtractor


def test_model_defaults():
    cfg = load_config(None)
    assert cfg.classify.model == "convaiinnovations/laya"
    assert cfg.classify.subfolder == "multilingual"
    assert cfg.classify.router_default == "multilingual"
    assert cfg.classify.router_preload == ("english", "multilingual")
    assert cfg.classify.device == "auto"
    assert cfg.classify.max_len == 8192
    assert cfg.media.whisper_model == "small"
    assert cfg.media.whisper_device == "cpu"
    assert cfg.media.whisper_compute_type == "int8"


def test_parse_str_list_comma_and_json():
    assert parse_value("str_list", "en,ru") == ["en", "ru"]
    assert parse_value("str_list", '["en", "ru"]') == ["en", "ru"]
    assert parse_value("str_list", "") == []
    assert parse_value("int", "12") == 12
    assert parse_value("float", "0.7") == 0.7
    assert parse_value("str", "medium") == "medium"


def test_set_roundtrip_preserves_other_sections(tmp_path):
    target = tmp_path / "config.toml"
    target.write_text('[media]\nwhisper_model = "small"\n')
    data = set_dotted_raw(load_raw(target), "media.whisper_model", "medium")
    save_raw(target, data)
    cfg = load_config(target)
    assert cfg.media.whisper_model == "medium"
    assert cfg.ocr.engine == "paddle"  # defaults intact

    data = set_dotted_raw(load_raw(target), "ocr.langs", ["en", "ru"])
    save_raw(target, data)
    assert load_config(target).ocr.langs == ("en", "ru")


def test_get_dotted_unknown_key_raises():
    cfg = load_config(None)
    with pytest.raises(KeyError):
        get_dotted(cfg, "nope.nope")
    assert format_value(("a", "b")) == "a,b"


def test_toml_overrides_reach_new_model_fields(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        "[classify]\n"
        'model = "org/custom"\n'
        'subfolder = ""\n'
        'router_default = "english"\n'
        'router_preload = ["english"]\n'
        'device = "cpu"\n'
        "max_len = 4096\n"
        "[media]\n"
        'whisper_model = "medium"\n'
        'whisper_device = "cuda"\n'
        'whisper_compute_type = "float16"\n'
    )
    cfg = load_config(config_file)
    assert cfg.classify.model == "org/custom"
    assert cfg.classify.subfolder == ""
    assert cfg.classify.router_preload == ("english",)
    assert cfg.classify.max_len == 4096
    assert cfg.media.whisper_device == "cuda"


def test_unknown_ocr_engine_fails_fast():
    with pytest.raises(ValueError, match="ocr.engine"):
        TextExtractor(OcrPolicy(engine="surya"))


def _fake_laya_module():
    calls: dict = {}
    mod = types.ModuleType("laya")

    class FakeRouter:
        def __init__(self, default=None, device=None):
            calls["router_default"] = default
            calls["router_device"] = device

        def preload(self, names):
            calls["preload"] = list(names)

        def predict(self, state, questions, max_len=None):
            calls["predict_max_len"] = max_len
            return {"answers": {"category": {"choice": "a", "answer_confidence": 0.9}},
                    "routing": {"model": "fake"}}

    def fake_load(model_id_or_path="convaiinnovations/laya", device=None, subfolder=None, **kw):
        calls["load_model"] = model_id_or_path
        calls["load_subfolder"] = subfolder
        calls["load_device"] = device
        return object()

    mod.Router = FakeRouter
    mod.load = fake_load
    mod.cached_embed_fn = lambda fn: fn
    mod.embed_fn_from_agent = lambda agent: (lambda text: [1.0])
    mod.predict_shortlist = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no shortlist expected"))
    mod.calls = calls  # type: ignore[attr-defined]
    return mod


def test_laya_engine_uses_policy(monkeypatch):
    mod = _fake_laya_module()
    monkeypatch.setitem(sys.modules, "laya", mod)
    policy = ClassifyPolicy(model="org/custom", subfolder="", router_default="english",
                            router_preload=("english",), device="cpu", max_len=4096,
                            shortlist_threshold=999)
    from embly.categories import Category

    engine = LayaEngine(policy)
    engine._get_agent()
    engine._get_router()
    cats = [Category(id=1, name="a", slug="a", description="d", status="active",
                     auto_created=False, centroid=None)]
    engine.decide({"subject": "x", "body": "y"}, cats)
    assert mod.calls["load_model"] == "org/custom"  # noqa
    assert mod.calls["load_subfolder"] is None  # empty string -> root checkpoint  # noqa
    assert mod.calls["router_default"] == "english"  # noqa
    assert mod.calls["preload"] == ["english"]  # noqa
    assert mod.calls["predict_max_len"] == 4096  # noqa


def test_laya_device_auto_means_none():
    assert LayaEngine(ClassifyPolicy(device="auto"))._laya_device() is None
    assert LayaEngine(ClassifyPolicy(device="cpu"))._laya_device() == "cpu"


def test_cli_config_set_get_roundtrip(tmp_path):
    runner = CliRunner()
    target = tmp_path / "config.toml"
    assert runner.invoke(app, ["config", "set", "media.whisper_model", "medium",
                               "--config", str(target)]).exit_code == 0
    got = runner.invoke(app, ["config", "get", "media.whisper_model", "--config", str(target)])
    assert got.exit_code == 0 and got.stdout.strip() == "medium"
    listed = runner.invoke(app, ["config", "list", "--config", str(target)])
    assert listed.exit_code == 0 and "media.whisper_model" in listed.stdout
    bad = runner.invoke(app, ["config", "set", "nope.nope", "x", "--config", str(target)])
    assert bad.exit_code == 1
    assert Path(target).exists()


def test_cli_config_set_list_value(tmp_path):
    runner = CliRunner()
    target = tmp_path / "config.toml"
    assert runner.invoke(app, ["config", "set", "ocr.langs", "en,ru",
                               "--config", str(target)]).exit_code == 0
    assert load_config(target).ocr.langs == ("en", "ru")
    assert MediaPolicy(whisper_model="medium").whisper_device == "cpu"
