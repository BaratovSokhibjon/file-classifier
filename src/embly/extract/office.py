from __future__ import annotations

from pathlib import Path

from embly.extract.base import ExtractContext, Extraction

OFFICE_EXTS = {
    ".docx", ".xlsx", ".pptx",
    ".eml", ".html", ".htm", ".csv", ".json",
}


def extract_office(path: Path, ctx: ExtractContext) -> Extraction:
    try:
        from markitdown import MarkItDown
    except ImportError:
        return Extraction("", "office-extra-not-installed", ok=False)
    result = MarkItDown().convert(str(path))
    return Extraction(result.text_content or "", "markitdown")
