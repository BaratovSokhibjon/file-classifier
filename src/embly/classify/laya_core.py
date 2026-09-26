from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from embly.categories import Category
from embly.config import ClassifyPolicy


@dataclass(frozen=True)
class Decision:
    choice: str
    confidence: float
    model: str
    ms: float
    shortlist_json: str | None = None


@runtime_checkable
class DecisionEngine(Protocol):
    """The seam in front of laya. Production uses :class:`LayaEngine`; tests pass a fake,
    so classification can be exercised without downloading checkpoints."""

    def decide(self, state: dict, categories: list[Category]) -> Decision:
        ...

    def embed(self, text: str) -> list[float]:
        ...

    def clear_cache(self) -> None:
        ...


def build_state(name: str, text: str, max_tokens: int) -> dict:
    return {"subject": name, "body": text[:max_tokens * 4]}


def build_questions(categories: list[Category]) -> dict:
    criteria = {c.slug: c.description for c in categories}
    return {
        "category": {
            "type": "choice",
            "instructions": "Which category does this document belong to?",
            "criteria": criteria,
        }
    }


class LayaEngine:
    """Production ``DecisionEngine`` adapter over laya.

    Owns the checkpoints, the shortlist-vs-router strategy, and the embedding function.
    Nothing is a module global, so two engines can coexist and tests never touch this.
    """

    def __init__(self, policy: ClassifyPolicy) -> None:
        self._policy = policy
        self._router: Any = None
        self._agent: Any = None
        self._embed_fn: Any = None

    def decide(self, state: dict, categories: list[Category]) -> Decision:
        import laya

        questions = build_questions(categories)
        started = time.time()
        if len(categories) > self._policy.shortlist_threshold:
            k = min(self._policy.shortlist_k, len(categories))
            result = laya.predict_shortlist(
                self._get_agent(), state, questions, embed_fn=self._get_embed_fn(), k=k
            )
        else:
            result = self._get_router().predict(state, questions, max_len=self._policy.max_len)
        answer = result["answers"]["category"]
        return Decision(
            choice=answer["choice"],
            confidence=float(answer["answer_confidence"]),
            model=result["routing"]["model"],
            ms=(time.time() - started) * 1000,
            shortlist_json=json.dumps(result["answers"]["category"]),
        )

    def embed(self, text: str) -> list[float]:
        return list(self._get_embed_fn()(text))

    def clear_cache(self) -> None:
        if self._embed_fn is None:
            return
        for name in ("cache_clear", "clear"):
            clear = getattr(self._embed_fn, name, None)
            if callable(clear):
                clear()
                return

    def _laya_device(self) -> Any:
        return None if self._policy.device == "auto" else self._policy.device

    def _get_router(self) -> Any:
        if self._router is None:
            import laya

            self._router = laya.Router(default=self._policy.router_default, device=self._laya_device())
            preload = list(self._policy.router_preload)
            if preload:
                self._router.preload(preload)
        return self._router

    def _get_agent(self) -> Any:
        if self._agent is None:
            import laya

            subfolder = self._policy.subfolder or None
            self._agent = laya.load(self._policy.model, subfolder=subfolder, device=self._laya_device())
        return self._agent

    def _get_embed_fn(self) -> Any:
        if self._embed_fn is None:
            import laya

            self._embed_fn = laya.cached_embed_fn(laya.embed_fn_from_agent(self._get_agent()))
        return self._embed_fn
