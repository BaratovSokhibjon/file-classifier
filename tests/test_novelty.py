from __future__ import annotations

import numpy as np

from embly.classify.naming_llm import NamingClient
from embly.classify.novelty import (
    NovelItem,
    bytes_to_vec,
    centroid_to_vec,
    cluster_by_cosine,
    cosine_similarity,
    vec_to_bytes,
)
from embly.config import NamingLlmPolicy


def test_vec_roundtrip():
    original = [1.0, 2.5, -3.0, 0.5]
    restored = bytes_to_vec(vec_to_bytes(original))
    assert np.allclose(restored, original, atol=1e-5)


def test_centroid_unpacks_little_endian():
    import struct

    packed = struct.pack("<3f", 1.0, 2.0, 3.0)
    assert np.allclose(centroid_to_vec(packed), [1.0, 2.0, 3.0])


def test_cosine_similarity_basic():
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    assert cosine_similarity(a, b) == 0.0
    assert abs(cosine_similarity(a, a) - 1.0) < 1e-5
    c = np.array([1.0, 1.0, 0.0], dtype=np.float32)
    assert abs(cosine_similarity(a, c) - 0.7071) < 0.01


def test_cosine_similarity_zero_vector():
    z = np.zeros(3, dtype=np.float32)
    a = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    assert cosine_similarity(z, a) == 0.0


def test_cluster_single_linkage_merges():
    items = [
        NovelItem(1, "a", "a", np.array([1.0, 0.0], dtype=np.float32)),
        NovelItem(2, "b", "b", np.array([0.95, 0.05], dtype=np.float32)),
        NovelItem(3, "c", "c", np.array([0.0, 1.0], dtype=np.float32)),
    ]
    clusters = cluster_by_cosine(items, threshold=0.85)
    assert len(clusters) == 2
    big = max(clusters, key=lambda c: len(c.items))
    assert {item.file_id for item in big.items} == {1, 2}


def test_cluster_all_singletons():
    items = [
        NovelItem(1, "a", "a", np.array([1.0, 0.0], dtype=np.float32)),
        NovelItem(2, "b", "b", np.array([0.0, 1.0], dtype=np.float32)),
    ]
    clusters = cluster_by_cosine(items, threshold=0.99)
    assert len(clusters) == 2
    assert all(len(c.items) == 1 for c in clusters)


def test_cluster_empty():
    assert cluster_by_cosine([], threshold=0.5) == []


def test_cluster_sorted_largest_first():
    items = [
        NovelItem(i, f"s{i}", f"f{i}", vec)
        for i, vec in enumerate([
            np.array([1.0, 0.0], dtype=np.float32),
            np.array([0.99, 0.01], dtype=np.float32),
            np.array([0.98, 0.02], dtype=np.float32),
            np.array([0.0, 1.0], dtype=np.float32),
        ])
    ]
    clusters = cluster_by_cosine(items, threshold=0.9)
    assert len(clusters[0].items) >= len(clusters[-1].items)
    assert len(clusters[0].items) == 3


def test_naming_client_manual_mode():
    client = NamingClient(NamingLlmPolicy(mode="manual"))
    result = client.name_cluster(["some text"], fallback_index=2)
    assert result.name == "cluster-3" and "auto" in result.description
    assert result.used_llm is False


def test_naming_client_fallback_on_connection_error(monkeypatch):
    import urllib.request

    def boom(*args, **kwargs):
        raise OSError("unreachable")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    client = NamingClient(NamingLlmPolicy(mode="llm"))
    result = client.name_cluster(["text"], fallback_index=0)
    assert result.name == "cluster-1" and "auto" in result.description
    assert result.used_llm is False


def test_naming_client_parse_json_response():
    text = '{"name": "books", "description": "PDF books and ebooks"}'
    name, desc = NamingClient._parse_response(text)
    assert name == "books" and desc == "PDF books and ebooks"


def test_naming_client_parse_json_with_backticks():
    text = '```json\n{"name": "photos", "description": "personal photos"}\n```'
    name, desc = NamingClient._parse_response(text)
    assert name == "photos" and desc == "personal photos"


def test_naming_client_parse_fallback_lines():
    text = "invoices\nbilling documents"
    name, desc = NamingClient._parse_response(text)
    assert name == "invoices" and desc == "billing documents"
