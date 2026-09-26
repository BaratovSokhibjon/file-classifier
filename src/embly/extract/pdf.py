from __future__ import annotations

from pathlib import Path

from embly.extract.base import ExtractContext, Extraction, _temp_dir, run_ocr

PDF_EXTS = {".pdf"}
_MIN_NATIVE_CHARS_PER_PAGE = 100


def extract_pdf(path: Path, ctx: ExtractContext) -> Extraction:
    import pymupdf

    doc = pymupdf.open(path)
    try:
        text = "\n".join(page.get_text() for page in doc)
        if doc.page_count > 0 and len(text.strip()) / doc.page_count >= _MIN_NATIVE_CHARS_PER_PAGE:
            return Extraction(text, f"pdf-native({doc.page_count}p)")
        if doc.page_count == 0:
            return Extraction("", "pdf-empty", ok=False)
        pages = min(doc.page_count, ctx.ocr.max_pdf_ocr_pages)
        with _temp_dir() as tmp:
            for i in range(pages):
                doc[i].get_pixmap(dpi=ctx.ocr.rasterize_dpi).save(tmp / f"p{i}.png")
            images = [tmp / f"p{i}.png" for i in range(pages)]
            return run_ocr(images, ctx)
    finally:
        doc.close()
