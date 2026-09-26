from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def vec_to_bytes(vec: list[float]) -> bytes:
    return np.array(vec, dtype=np.float32).tobytes()


def bytes_to_vec(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.float32).copy()


def centroid_to_vec(data: bytes) -> np.ndarray:
    """Category centroids are packed little-endian (``struct.pack('<Nf', ...)``)."""
    return np.frombuffer(data, dtype="<f4").copy()


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


@dataclass(frozen=True)
class NovelItem:
    file_id: int
    sha: str
    original_name: str
    vec: np.ndarray


@dataclass(frozen=True)
class Cluster:
    items: list[NovelItem]


def cluster_by_cosine(items: list[NovelItem], threshold: float) -> list[Cluster]:
    """Single-linkage clustering: two items join if cosine-sim >= threshold.

    Returns clusters sorted largest-first; singletons are included.
    """
    n = len(items)
    if n == 0:
        return []

    embeddings = np.array([item.vec for item in items], dtype=np.float32)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normalized = embeddings / norms
    sim = normalized @ normalized.T

    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i in range(n):
        for j in range(i + 1, n):
            if sim[i, j] >= threshold:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    return [
        Cluster(items=[items[i] for i in indices])
        for indices in sorted(groups.values(), key=len, reverse=True)
    ]
