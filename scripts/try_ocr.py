#!/usr/bin/env python
"""OCR an image or scanned PDF with PaddleOCR, optionally categorize the text with laya.

A thin probe over the embly package — the OCR language strategy and the laya
wiring live in the package, not here.

Usage:
    .venv/bin/python scripts/try_ocr.py scan.png
    .venv/bin/python scripts/try_ocr.py scan.pdf --lang uz
    .venv/bin/python scripts/try_ocr.py --render samples/invoice_uz.txt --lang uz --classify
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
import warnings
from pathlib import Path

from try_laya import DEFAULT_CATEGORIES, as_categories

from embly.classify import LayaEngine
from embly.config import ClassifyPolicy
from embly.extract.engines import PaddleEngine

warnings.filterwarnings("ignore")

FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"


def render_to_image(text: str, out: Path, font_size: int = 34, width: int = 1500) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(FONT, font_size)
    wrapped: list[str] = []
    for raw in text.splitlines():
        while len(raw) > 64:
            wrapped.append(raw[:64])
            raw = raw[64:]
        wrapped.append(raw)
    line_h = font_size + 14
    img = Image.new("RGB", (width, 40 * 2 + line_h * len(wrapped)), "white")
    draw = ImageDraw.Draw(img)
    y = 40
    for line in wrapped:
        draw.text((40, y), line, fill="black", font=font)
        y += line_h
    img.save(out)
    return out


def pdf_to_images(path: Path, dpi: int = 300, max_pages: int = 5) -> list[Path]:
    import pymupdf

    doc = pymupdf.open(path)
    out: list[Path] = []
    tmp = Path(tempfile.mkdtemp())
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        target = tmp / f"page{i}.png"
        page.get_pixmap(dpi=dpi).save(target)
        out.append(target)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", type=Path, help="image or PDF to OCR")
    ap.add_argument("--render", type=Path, help="render this text file to a synthetic scan first")
    ap.add_argument("--lang", default="en", help="PaddleOCR language code (en, uz, ru, ...)")
    ap.add_argument("--classify", action="store_true", help="categorize the OCR text with laya")
    args = ap.parse_args()

    if args.render:
        tmp = Path(tempfile.mkdtemp()) / "scan.png"
        render_to_image(args.render.read_text(errors="ignore"), tmp)
        images = [tmp]
        print(f"rendered {args.render} -> {tmp}", file=sys.stderr)
    elif args.path and args.path.suffix.lower() == ".pdf":
        images = pdf_to_images(args.path)
    elif args.path:
        images = [args.path]
    else:
        ap.error("provide a path or --render")

    engine = PaddleEngine()
    t0 = time.time()
    texts: list[str] = []
    scores: list[float] = []
    for image in images:
        found, found_scores = engine.recognize(image, args.lang)
        texts += found
        scores += found_scores
    mean = sum(scores) / len(scores) if scores else 0.0
    text = "\n".join(texts)
    print(f"\n--- OCR ({args.lang}, {time.time() - t0:.1f}s, mean conf {mean:.3f}) ---")
    print(text)

    if args.classify:
        laya = LayaEngine(ClassifyPolicy())
        decision = laya.decide(
            {"subject": Path(args.render or args.path).name, "body": text[:8000]},
            as_categories(DEFAULT_CATEGORIES),
        )
        print(f"\n--- laya (routed to {decision.model}) ---")
        print(f"category={decision.choice}  answer_confidence={decision.confidence:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
