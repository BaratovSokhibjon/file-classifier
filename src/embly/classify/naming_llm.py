from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

from embly.config import NamingLlmPolicy


@dataclass(frozen=True)
class NamingResult:
    name: str
    description: str
    used_llm: bool


class NamingClient:
    """Ask a local Ollama server to name a cluster of documents.

    No dependency on the ``ollama`` package — calls the REST API with stdlib
    ``urllib``. Falls back to a generic name when the server is unreachable
    or ``mode == 'manual'``; callers warn on fallback via ``used_llm``.
    """

    def __init__(self, policy: NamingLlmPolicy) -> None:
        self._policy = policy

    def name_cluster(self, excerpts: list[str], fallback_index: int = 0) -> NamingResult:
        """Return a ``(name, description)`` result for a cluster of document excerpts."""
        if self._policy.mode == "manual":
            return self._fallback(fallback_index)
        try:
            name, description = self._ask_ollama(excerpts)
            return NamingResult(name=name, description=description, used_llm=True)
        except Exception:  # noqa: BLE001
            return self._fallback(fallback_index)

    def _ask_ollama(self, excerpts: list[str]) -> tuple[str, str]:
        sample = "\n\n".join(
            f"--- Document {i + 1} ---\n{txt[:500]}" for i, txt in enumerate(excerpts[:5])
        )
        prompt = (
            "You are organizing files into categories. "
            "Given these document excerpts, suggest a short category name (1-3 words, "
            "lowercase, hyphens) and a one-line description.\n\n"
            f"{sample}\n\n"
            'Respond as JSON only: {"name": "...", "description": "..."}'
        )
        body = json.dumps({
            "model": self._policy.model,
            "prompt": prompt,
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            f"{self._policy.host}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        text = result.get("response", "").strip()
        return self._parse_response(text)

    @staticmethod
    def _parse_response(text: str) -> tuple[str, str]:
        for candidate in (text, text.strip("`").removeprefix("json").strip()):
            try:
                obj = json.loads(candidate)
                name = str(obj.get("name", "")).strip()
                desc = str(obj.get("description", "")).strip()
                if name and desc:
                    return name, desc
            except (json.JSONDecodeError, ValueError):
                continue
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if len(lines) >= 2:
            return lines[0], lines[1]
        if len(lines) == 1:
            return lines[0], lines[0]
        return "cluster", "auto-discovered cluster"

    @staticmethod
    def _fallback(index: int) -> NamingResult:
        return NamingResult(
            name=f"cluster-{index + 1}", description="auto-discovered category", used_llm=False
        )
