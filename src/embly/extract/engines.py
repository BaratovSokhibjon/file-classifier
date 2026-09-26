from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class OcrEngine(Protocol):
    """The seam that lets the OCR engine be swapped (or faked in tests).

    One call handles one language; the language strategy lives in the extraction
    module, not here.
    """

    def recognize(self, path: Path, lang: str) -> tuple[list[str], list[float]]:
        ...


class PaddleEngine:
    """Production ``OcrEngine`` adapter over PaddleOCR (PP-OCRv5)."""

    def __init__(self) -> None:
        self._instances: dict[str, Any] = {}

    def _ocr(self, lang: str) -> Any:
        if lang not in self._instances:
            from paddleocr import PaddleOCR

            self._instances[lang] = PaddleOCR(
                lang=lang,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        return self._instances[lang]

    def recognize(self, path: Path, lang: str) -> tuple[list[str], list[float]]:
        texts: list[str] = []
        scores: list[float] = []
        for page in self._ocr(lang).predict(str(path)):
            data = _page_dict(page)
            texts += [t for t in (data.get("rec_texts") or []) if t]
            scores += [float(s) for s in (data.get("rec_scores") or [])]
        return texts, scores


def _page_dict(page: Any) -> dict:
    if isinstance(page, dict):
        return page
    try:
        return dict(page)
    except Exception:  # noqa: BLE001
        return dict(page.json.get("res", {}))
