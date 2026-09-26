#!/usr/bin/env python
"""Classify files into categories with laya — a thin probe over the embly package.

Usage:
    .venv/bin/python scripts/try_laya.py samples/
    .venv/bin/python scripts/try_laya.py ~/Downloads --categories categories.json
    .venv/bin/python scripts/try_laya.py some.pdf --show-text
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

from embly.categories import Category
from embly.classify import LayaEngine
from embly.config import ClassifyPolicy, OcrPolicy
from embly.extract import TextExtractor, gather

warnings.filterwarnings("ignore")

DEFAULT_CATEGORIES = {
    "invoice": "bills, invoices, payment requests, amounts due, tax, faktura",
    "receipt": "proof of purchase, transaction confirmations, till receipts",
    "contract": "legal agreements, contracts, NDAs, terms, signatures, dogovor",
    "identity": "passports, ID cards, driver licenses, birth certificates",
    "medical": "prescriptions, lab results, medical reports, diagnoses",
    "travel": "tickets, itineraries, boarding passes, hotel bookings",
    "statement": "bank statements, account summaries, balances",
    "correspondence": "letters, emails, memos, personal or business communication",
    "other": "anything that does not fit the categories above",
}


def as_categories(mapping: dict[str, str]) -> list[Category]:
    """The probe's sample categories as the domain objects classify speaks in."""
    return [
        Category(id=0, name=slug, slug=slug, description=description,
                 status="active", auto_created=0, centroid=None)
        for slug, description in mapping.items()
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="files or directories")
    ap.add_argument("--categories", type=Path, help="JSON file mapping slug -> description")
    ap.add_argument("--max-len", type=int, default=8192)
    ap.add_argument("--chars", type=int, default=8000, help="max characters of text fed to the model")
    ap.add_argument("--show-text", action="store_true", help="print extracted text to stderr")
    args = ap.parse_args()

    mapping = json.loads(args.categories.read_text()) if args.categories else DEFAULT_CATEGORIES
    categories = as_categories(mapping)
    files = gather([Path(p) for p in args.paths])
    if not files:
        print("no input files", file=sys.stderr)
        return 1

    extractor = TextExtractor(OcrPolicy())
    engine = LayaEngine(ClassifyPolicy(), max_len=args.max_len)
    print(f"{len(files)} file(s), {len(categories)} categories — loading laya...", file=sys.stderr)

    rows: list[tuple[str, str, float | None, str, float]] = []
    for path in files:
        extraction = extractor.extract(path)
        if not extraction.text.strip():
            rows.append((path.name, "—", None, extraction.source, 0.0))
            print(f"  SKIP  {path.name}: {extraction.source}", file=sys.stderr)
            continue
        if args.show_text:
            print(f"\n----- {path.name} ({extraction.source}) -----\n{extraction.text[:1000]}\n", file=sys.stderr)
        decision = engine.decide(
            {"subject": path.name, "body": extraction.text[: args.chars]}, categories
        )
        rows.append((path.name, decision.choice, decision.confidence,
                     f"{extraction.source} | {decision.model}", decision.ms))

    width = max((len(r[0]) for r in rows), default=8)
    print()
    print(f"{'file'.ljust(width)}  {'category'.ljust(13)}  {'conf':>5}  {'ms':>6}  routing")
    print("-" * (width + 45))
    for name, choice, confidence, how, ms in rows:
        shown = f"{confidence:.3f}" if confidence is not None else "  -  "
        print(f"{name.ljust(width)}  {choice.ljust(13)}  {shown:>5}  {ms:6.0f}  {how}")

    counts: dict[str, int] = {}
    for _, choice, _, _, _ in rows:
        counts[choice] = counts.get(choice, 0) + 1
    print("\nsummary: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
