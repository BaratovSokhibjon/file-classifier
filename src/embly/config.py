from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ROOT = "~/Documents/embly"


@dataclass(frozen=True)
class Paths:
    root: Path
    inbox: Path
    organized: Path
    unsorted: Path
    db: Path
    texts: Path
    logs: Path


@dataclass(frozen=True)
class OcrPolicy:
    engine: str = "paddle"
    langs: tuple[str, ...] = ("uz", "ru", "en")
    min_mean_confidence: float = 0.80
    rasterize_dpi: int = 300
    max_pdf_ocr_pages: int = 50


@dataclass(frozen=True)
class ClassifyPolicy:
    shortlist_k: int = 12
    shortlist_threshold: int = 16
    assign_confidence: float = 0.70
    review_confidence: float = 0.45
    max_text_tokens: int = 3000
    batch_size: int = 32
    model: str = "convaiinnovations/laya"
    subfolder: str = "multilingual"
    router_default: str = "multilingual"
    router_preload: tuple[str, ...] = ("english", "multilingual")
    device: str = "auto"
    max_len: int = 8192


@dataclass(frozen=True)
class NamingPolicy:
    template: str = "{date}_{category}_{slug}"


@dataclass(frozen=True)
class NoveltyPolicy:
    cosine: float = 0.55
    cluster_cosine: float = 0.75


@dataclass(frozen=True)
class NamingLlmPolicy:
    mode: str = "llm"
    model: str = "qwen3:4b"
    host: str = "http://127.0.0.1:11434"


@dataclass(frozen=True)
class MediaPolicy:
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    ffmpeg: str = "ffmpeg"


@dataclass(frozen=True)
class DedupePolicy:
    on_duplicate: str = "skip"


@dataclass(frozen=True)
class Config:
    paths: Paths
    ocr: OcrPolicy = field(default_factory=OcrPolicy)
    classify: ClassifyPolicy = field(default_factory=ClassifyPolicy)
    naming: NamingPolicy = field(default_factory=NamingPolicy)
    novelty: NoveltyPolicy = field(default_factory=NoveltyPolicy)
    naming_llm: NamingLlmPolicy = field(default_factory=NamingLlmPolicy)
    media: MediaPolicy = field(default_factory=MediaPolicy)
    dedupe: DedupePolicy = field(default_factory=DedupePolicy)

    def ensure_dirs(self) -> None:
        self.paths.texts.mkdir(parents=True, exist_ok=True)
        self.paths.logs.mkdir(parents=True, exist_ok=True)


def _find_config(explicit: Path | None) -> Path | None:
    if explicit:
        return explicit
    for cand in (Path.cwd() / "config.toml", Path.home() / ".config/embly/config.toml"):
        if cand.exists():
            return cand
    return None


def load_config(explicit: Path | None = None) -> Config:
    path = _find_config(explicit)
    data: dict = {}
    if path and Path(path).exists():
        data = tomllib.loads(Path(path).read_text())

    raw_paths = data.get("paths", {})
    root = Path(raw_paths.get("root", DEFAULT_ROOT)).expanduser()
    paths = Paths(
        root=root,
        inbox=Path(raw_paths.get("inbox", str(root / "inbox"))).expanduser(),
        organized=Path(raw_paths.get("organized", str(root / "organized"))).expanduser(),
        unsorted=Path(raw_paths.get("unsorted", str(root / "unsorted"))).expanduser(),
        db=Path(raw_paths.get("db", str(root / ".embly/embly.db"))).expanduser(),
        texts=Path(raw_paths.get("texts", str(root / ".embly/texts"))).expanduser(),
        logs=Path(raw_paths.get("logs", str(root / ".embly/logs"))).expanduser(),
    )

    naming = data.get("naming", {})
    naming_policy = NamingPolicy(template=naming.get("template", NamingPolicy.template))

    ocr = data.get("ocr", {})
    default_ocr = OcrPolicy()
    ocr_policy = OcrPolicy(
        engine=ocr.get("engine", default_ocr.engine),
        langs=tuple(ocr.get("langs", default_ocr.langs)),
        min_mean_confidence=float(ocr.get("min_mean_confidence", default_ocr.min_mean_confidence)),
        rasterize_dpi=int(ocr.get("rasterize_dpi", default_ocr.rasterize_dpi)),
        max_pdf_ocr_pages=int(ocr.get("max_pdf_ocr_pages", default_ocr.max_pdf_ocr_pages)),
    )

    classify = data.get("classify", {})
    default_classify = ClassifyPolicy()
    classify_policy = ClassifyPolicy(
        shortlist_k=int(classify.get("shortlist_k", default_classify.shortlist_k)),
        shortlist_threshold=int(classify.get("shortlist_threshold", default_classify.shortlist_threshold)),
        assign_confidence=float(classify.get("assign_confidence", default_classify.assign_confidence)),
        review_confidence=float(classify.get("review_confidence", default_classify.review_confidence)),
        max_text_tokens=int(classify.get("max_text_tokens", default_classify.max_text_tokens)),
        batch_size=int(classify.get("batch_size", default_classify.batch_size)),
        model=str(classify.get("model", default_classify.model)),
        subfolder=str(classify.get("subfolder", default_classify.subfolder)),
        router_default=str(classify.get("router_default", default_classify.router_default)),
        router_preload=tuple(classify.get("router_preload", default_classify.router_preload)),
        device=str(classify.get("device", default_classify.device)),
        max_len=int(classify.get("max_len", default_classify.max_len)),
    )

    novelty = data.get("novelty", {})
    default_novelty = NoveltyPolicy()
    novelty_policy = NoveltyPolicy(
        cosine=float(novelty.get("cosine", default_novelty.cosine)),
        cluster_cosine=float(novelty.get("cluster_cosine", default_novelty.cluster_cosine)),
    )

    naming_llm = data.get("naming_llm", {})
    default_llm = NamingLlmPolicy()
    naming_llm_policy = NamingLlmPolicy(
        mode=naming_llm.get("mode", default_llm.mode),
        model=naming_llm.get("model", default_llm.model),
        host=naming_llm.get("host", default_llm.host),
    )

    media = data.get("media", {})
    default_media = MediaPolicy()
    media_policy = MediaPolicy(
        whisper_model=media.get("whisper_model", default_media.whisper_model),
        whisper_device=media.get("whisper_device", default_media.whisper_device),
        whisper_compute_type=media.get("whisper_compute_type", default_media.whisper_compute_type),
        ffmpeg=media.get("ffmpeg", default_media.ffmpeg),
    )

    dedupe = data.get("dedupe", {})
    default_dedupe = DedupePolicy()
    dedupe_policy = DedupePolicy(
        on_duplicate=dedupe.get("on_duplicate", default_dedupe.on_duplicate),
    )

    return Config(
        paths=paths,
        ocr=ocr_policy,
        classify=classify_policy,
        naming=naming_policy,
        novelty=novelty_policy,
        naming_llm=naming_llm_policy,
        media=media_policy,
        dedupe=dedupe_policy,
    )


# --- CLI-editable model/settings registry + TOML persistence ---

# dotted key -> (section, field, kind) where kind drives value parsing.
# Covers all model knobs plus the thresholds users tune alongside them.
SETTABLE_KEYS: dict[str, tuple[str, str, str]] = {
    "ocr.engine": ("ocr", "engine", "str"),
    "ocr.langs": ("ocr", "langs", "str_list"),
    "ocr.min_mean_confidence": ("ocr", "min_mean_confidence", "float"),
    "ocr.rasterize_dpi": ("ocr", "rasterize_dpi", "int"),
    "ocr.max_pdf_ocr_pages": ("ocr", "max_pdf_ocr_pages", "int"),
    "classify.model": ("classify", "model", "str"),
    "classify.subfolder": ("classify", "subfolder", "str"),
    "classify.router_default": ("classify", "router_default", "str"),
    "classify.router_preload": ("classify", "router_preload", "str_list"),
    "classify.device": ("classify", "device", "str"),
    "classify.max_len": ("classify", "max_len", "int"),
    "classify.shortlist_k": ("classify", "shortlist_k", "int"),
    "classify.shortlist_threshold": ("classify", "shortlist_threshold", "int"),
    "classify.assign_confidence": ("classify", "assign_confidence", "float"),
    "classify.review_confidence": ("classify", "review_confidence", "float"),
    "classify.max_text_tokens": ("classify", "max_text_tokens", "int"),
    "classify.batch_size": ("classify", "batch_size", "int"),
    "media.whisper_model": ("media", "whisper_model", "str"),
    "media.whisper_device": ("media", "whisper_device", "str"),
    "media.whisper_compute_type": ("media", "whisper_compute_type", "str"),
    "media.ffmpeg": ("media", "ffmpeg", "str"),
    "naming_llm.mode": ("naming_llm", "mode", "str"),
    "naming_llm.model": ("naming_llm", "model", "str"),
    "naming_llm.host": ("naming_llm", "host", "str"),
    "naming.template": ("naming", "template", "str"),
    "novelty.cosine": ("novelty", "cosine", "float"),
    "novelty.cluster_cosine": ("novelty", "cluster_cosine", "float"),
    "dedupe.on_duplicate": ("dedupe", "on_duplicate", "str"),
}


def resolve_config_path(explicit: Path | None = None, *, for_write: bool = False) -> Path:
    """Where to read from (or write to). For writes, create a home if none exists."""
    found = _find_config(explicit)
    if found is not None:
        return Path(found)
    if explicit is not None:
        return Path(explicit)
    if for_write:
        home = Path.home() / ".config/embly/config.toml"
        if (Path.cwd() / "config.toml").exists() or Path.cwd() == home.parent:
            return Path.cwd() / "config.toml"
        return home
    return Path.cwd() / "config.toml"


def load_raw(path: Path) -> dict:
    if path.exists():
        return tomllib.loads(path.read_text())
    return {}


def get_dotted(cfg: Config, key: str) -> object:
    if key not in SETTABLE_KEYS:
        raise KeyError(f"unknown config key: {key} (see `embly config list`)")
    section, fname, _ = SETTABLE_KEYS[key]
    return getattr(getattr(cfg, section), fname)


def parse_value(kind: str, raw: str) -> object:
    if kind == "str":
        return raw
    if kind == "int":
        return int(raw)
    if kind == "float":
        return float(raw)
    if kind == "str_list":
        text = raw.strip()
        if text.startswith("["):
            import json

            items = json.loads(text)
            return [str(x) for x in items]
        return [p.strip() for p in text.split(",") if p.strip()]
    raise ValueError(f"unknown kind: {kind}")


def format_value(value: object) -> str:
    if isinstance(value, (list, tuple)):
        return ",".join(str(v) for v in value)
    return str(value)


def set_dotted_raw(data: dict, key: str, value: object) -> dict:
    if key not in SETTABLE_KEYS:
        raise KeyError(f"unknown config key: {key} (see `embly config list`)")
    section, fname, _ = SETTABLE_KEYS[key]
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in data.items()}
    sect = dict(out.get(section, {}))
    sect[fname] = list(value) if isinstance(value, tuple) else value
    out[section] = sect
    return out


def save_raw(path: Path, data: dict) -> None:
    import tomli_w

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomli_w.dumps(data))
