from __future__ import annotations

from pathlib import Path

from charset_normalizer import from_bytes

from embly.extract.base import ExtractContext, Extraction

TEXT_EXTS = {
    ".txt", ".md", ".log", ".rst", ".tex", ".srt", ".xml",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".py", ".js", ".ts",
}


def extract_plain(path: Path, ctx: ExtractContext) -> Extraction:
    data = path.read_bytes()
    if not data:
        return Extraction("", "empty", ok=False)
    best = from_bytes(data).best()
    text = str(best) if best else data.decode("utf-8", "ignore")
    return Extraction(text, "text")
