from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from embly.extract.base import ExtractContext, Extraction, _temp_dir

MEDIA_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mov", ".mp4"}


def extract_media(path: Path, ctx: ExtractContext) -> Extraction:
    if shutil.which(ctx.media.ffmpeg) is None:
        return Extraction("", "ffmpeg-not-installed", ok=False)
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return Extraction("", "media-extra-not-installed", ok=False)

    with _temp_dir() as tmp:
        wav = tmp / "audio.wav"
        subprocess.run(
            [ctx.media.ffmpeg, "-nostdin", "-loglevel", "error", "-i", str(path),
             "-ac", "1", "-ar", "16000", str(wav)],
            check=True,
        )
        model = WhisperModel(
            ctx.media.whisper_model,
            device=ctx.media.whisper_device,
            compute_type=ctx.media.whisper_compute_type,
        )
        segments, _ = model.transcribe(str(wav))
        return Extraction("\n".join(seg.text.strip() for seg in segments), "whisper")
