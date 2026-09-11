"""Cosine-similarity matching of a speech-segment embedding against
enrolled voice profiles."""
from __future__ import annotations

from typing import Optional

import numpy as np

from app.core.interfaces import SpeakerProfileStore


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def match_speaker(
    embedding: np.ndarray, store: SpeakerProfileStore, threshold: float
) -> Optional[tuple[str, str, float]]:
    best: Optional[tuple[str, str, float]] = None
    for profile_id, profile_embedding in store.all_embeddings():
        score = cosine_similarity(embedding, profile_embedding)
        if score >= threshold and (best is None or score > best[2]):
            profile = store.get(profile_id)
            name = profile.name if profile else profile_id
            best = (profile_id, name, score)
    return best
