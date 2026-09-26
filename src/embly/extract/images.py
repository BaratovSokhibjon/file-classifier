from __future__ import annotations

from pathlib import Path

from embly.extract.base import ExtractContext, Extraction, _temp_dir, run_ocr

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".heic", ".heif"}


def extract_image(path: Path, ctx: ExtractContext) -> Extraction:
    with _temp_dir() as tmp:
        if path.suffix.lower() in {".heic", ".heif"}:
            path = _to_png(path, tmp)
        return run_ocr([path], ctx)


def _to_png(path: Path, tmp: Path) -> Path:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    from PIL import Image

    out = tmp / "converted.png"
    Image.open(path).convert("RGB").save(out)
    return out
