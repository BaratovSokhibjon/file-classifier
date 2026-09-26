from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from embly.config import MediaPolicy, OcrPolicy
from embly.extract.engines import OcrEngine, PaddleEngine


@dataclass(frozen=True)
class Extraction:
    """What a caller gets back: the text, which extractor produced it, and whether it worked."""

    text: str
    source: str
    ok: bool = True


@dataclass(frozen=True)
class ExtractContext:
    """Everything a format handler needs, handed to it by the module."""

    ocr: OcrPolicy
    engine: OcrEngine
    media: MediaPolicy = MediaPolicy()


Handler = Callable[[Path, ExtractContext], Extraction]


@contextmanager
def _temp_dir() -> Iterator[Path]:
    d = Path(tempfile.mkdtemp())
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def run_ocr(paths: list[Path], ctx: ExtractContext) -> Extraction:
    """OCR language strategy: try each configured language, early-exit when one clears the
    confidence threshold, otherwise keep the best-scoring pass. No text anywhere
    (e.g. photos) → ``ocr:no-text`` instead of a blank source."""
    best_text, best_source, best_mean = "", "", -1.0
    for lang in ctx.ocr.langs:
        texts: list[str] = []
        scores: list[float] = []
        for path in paths:
            try:
                found, found_scores = ctx.engine.recognize(path, lang)
            except ModuleNotFoundError:
                return Extraction("", "ocr-extra-not-installed", ok=False)
            texts += found
            scores += found_scores
        mean = sum(scores) / len(scores) if scores else 0.0
        source = f"ocr:{lang}({mean:.2f})"
        if texts and mean >= ctx.ocr.min_mean_confidence:
            return Extraction("\n".join(texts), source)
        if (texts or scores) and mean >= best_mean:
            best_text, best_source, best_mean = "\n".join(texts), source, mean
    if best_source:
        return Extraction(best_text, best_source)
    return Extraction("", "ocr:no-text", ok=False)


class TextExtractor:
    """The extraction module.

    One interface — :meth:`extract` — hides the dispatch table, the extension sets,
    MIME sniffing, the OCR language strategy, and graceful degradation. The OCR engine
    is an injected dependency, so tests pass a fake and never load PaddleOCR.
    """

    def __init__(
        self, ocr: OcrPolicy, engine: OcrEngine | None = None, media: MediaPolicy | None = None
    ) -> None:
        if engine is None and ocr.engine != "paddle":
            raise ValueError(f"unknown ocr.engine: {ocr.engine!r} (only 'paddle' is implemented)")
        self._ctx = ExtractContext(ocr=ocr, engine=engine or PaddleEngine(), media=media or MediaPolicy())
        self._table = _dispatch_table()

    def extract(self, path: Path, mime: str | None = None) -> Extraction:
        handler = self._table.get(_resolve_ext(path, mime))
        if handler is None:
            return Extraction("", f"unsupported({path.suffix.lower() or 'no-ext'})", ok=False)
        try:
            return handler(path, self._ctx)
        except Exception as e:  # noqa: BLE001
            return Extraction("", f"error:{type(e).__name__}", ok=False)


def _handler_for(path: Path, mime: str | None, table: dict[str, Handler]) -> Handler | None:
    return table.get(_resolve_ext(path, mime))


def _dispatch_table() -> dict[str, Handler]:
    """The one dispatch table. A dict cannot hold two owners for one extension, and the
    explicit guard turns any future overlap into a loud error instead of silent order
    dependence."""
    from embly.extract import images, media, office, pdf, plain

    table: dict[str, Handler] = {}
    for exts, handler in (
        (images.IMAGE_EXTS, images.extract_image),
        (office.OFFICE_EXTS, office.extract_office),
        (pdf.PDF_EXTS, pdf.extract_pdf),
        (media.MEDIA_EXTS, media.extract_media),
        (plain.TEXT_EXTS, plain.extract_plain),
    ):
        for ext in exts:
            if ext in table:
                raise RuntimeError(f"extractor for {ext!r} is registered twice")
            table[ext] = handler
    table[""] = plain.extract_plain  # extension-less files are read as text
    return table


def _resolve_ext(path: Path, mime: str | None) -> str:
    if mime:
        import mimetypes

        guessed = mimetypes.guess_extension(mime.split(";", 1)[0].strip())
        if guessed:
            return guessed.lower()
    return path.suffix.lower()


def gather(paths: list[Path]) -> list[Path]:
    """Expand files and directories into a flat, sorted file list.

    Skips embly internals (``.embly/``) and hidden files/dirs so ingesting
    the root by mistake does not record the database as a document.
    """
    out: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            out += sorted(f for f in p.rglob("*") if f.is_file() and not _is_skipped(f))
        elif p.is_file():
            out.append(p)
    return out


def _is_skipped(path: Path) -> bool:
    return ".embly" in path.parts or any(part.startswith(".") for part in path.parts)
