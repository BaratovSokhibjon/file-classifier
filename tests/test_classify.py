from __future__ import annotations

from fakes import FakeDecisionEngine

from embly.categories import Category
from embly.classify import build_questions


def category(slug: str, description: str = "d") -> Category:
    return Category(id=0, name=slug, slug=slug, description=description,
                    status="active", auto_created=False, centroid=None)


def test_engine_decide_returns_choice():
    engine = FakeDecisionEngine(choice="travel", confidence=0.8)
    decision = engine.decide({"subject": "x", "body": "y"}, [category("travel")])
    assert decision.choice == "travel" and engine.calls == 1


def test_build_questions_maps_slug_to_description():
    questions = build_questions([category("invoice", "bills")])
    assert questions["category"]["criteria"] == {"invoice": "bills"}
    assert questions["category"]["type"] == "choice"
