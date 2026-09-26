from __future__ import annotations

from pathlib import Path

from embly.config import load_config


def test_defaults_are_grouped_policies():
    cfg = load_config(None)
    assert cfg.ocr.langs == ("uz", "ru", "en")
    assert cfg.classify.assign_confidence == 0.70
    assert cfg.classify.review_confidence == 0.45
    assert cfg.paths.inbox.name == "inbox"
    assert cfg.naming.template == "{date}_{category}_{slug}"


def test_toml_overrides_reach_the_right_policy(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        "[paths]\n"
        'root = "~/myfc"\n'
        "[ocr]\n"
        'langs = ["en"]\n'
        "min_mean_confidence = 0.5\n"
        "[classify]\n"
        "assign_confidence = 0.8\n"
        "max_text_tokens = 1000\n"
    )
    cfg = load_config(config_file)
    assert cfg.ocr.langs == ("en",)
    assert cfg.ocr.min_mean_confidence == 0.5
    assert cfg.classify.assign_confidence == 0.8
    assert cfg.classify.max_text_tokens == 1000
    assert cfg.paths.root == Path("~/myfc").expanduser()
    assert cfg.paths.db == Path("~/myfc/.embly/embly.db").expanduser()
