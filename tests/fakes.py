"""Test doubles for the injected seams: the decision engine, the OCR engine, extraction."""

from __future__ import annotations

from pathlib import Path

from embly.classify import Decision


class FakeDecisionEngine:
    def __init__(self, choice: str = "invoice", confidence: float = 0.9) -> None:
        self.choice = choice
        self.confidence = confidence
        self.calls = 0
        self.cleared = False
        self.last_state: dict | None = None
        self.last_categories: list | None = None

    def decide(self, state: dict, categories: list) -> Decision:
        self.calls += 1
        self.last_state = state
        self.last_categories = categories
        return Decision(choice=self.choice, confidence=self.confidence, model="fake", ms=1.0)

    def embed(self, text: str) -> list[float]:
        return [float(len(text)), 1.0, 0.0]

    def clear_cache(self) -> None:
        self.cleared = True


class FakeOcrEngine:
    def __init__(self, results: dict[str, tuple[list[str], list[float]]] | None = None) -> None:
        self.results = results or {}
        self.calls: list[tuple[str, str]] = []

    def recognize(self, path: Path, lang: str) -> tuple[list[str], list[float]]:
        self.calls.append((Path(path).name, lang))
        return self.results.get(lang, ([], []))
