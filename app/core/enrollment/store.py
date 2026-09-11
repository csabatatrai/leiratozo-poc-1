"""File-based persistence for enrolled voice profiles."""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from app.config import EnrollmentStoreSettings
from app.core.interfaces import SpeakerProfileStore
from app.schemas import SpeakerProfile

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,200}$")


class FileSpeakerProfileStore(SpeakerProfileStore):
    def __init__(self, path: str):
        self._dir = path
        os.makedirs(self._dir, exist_ok=True)
        self._lock = threading.Lock()

    def _file(self, profile_id: str) -> str:
        # profile_id can reach here straight from a URL path param
        # (DELETE /speakers/{profile_id}) — reject anything that isn't a
        # plain slug before it touches the filesystem, to rule out path
        # traversal (e.g. "../../etc/passwd") entirely.
        if not _SAFE_ID_RE.match(profile_id):
            raise ValueError(f"invalid speaker profile id: {profile_id!r}")
        return os.path.join(self._dir, f"{profile_id}.json")

    def _read(self, profile_id: str) -> Optional[dict]:
        try:
            path = self._file(profile_id)
        except ValueError:
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            return None

    def _write(self, profile_id: str, data: dict) -> None:
        with open(self._file(profile_id), "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def upsert(self, profile_id: str, name: str, embedding: np.ndarray, embedding_backend: str) -> None:
        with self._lock:
            existing = self._read(profile_id)
            now = datetime.now(timezone.utc).isoformat()
            new_vec = np.asarray(embedding, dtype=np.float64)

            if existing is None:
                vec = new_vec
                n = 1
                created_at = now
            else:
                old_vec = np.asarray(existing["embedding"], dtype=np.float64)
                n = int(existing["num_enrollment_samples"])
                # running mean, weighted by how many samples went into the old vector
                vec = (old_vec * n + new_vec) / (n + 1)
                n += 1
                created_at = existing["created_at"]

            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm

            self._write(
                profile_id,
                {
                    "id": profile_id,
                    "name": name,
                    "embedding": vec.tolist(),
                    "embedding_backend": embedding_backend,
                    "created_at": created_at,
                    "updated_at": now,
                    "num_enrollment_samples": n,
                },
            )

    def _to_profile(self, data: dict) -> SpeakerProfile:
        return SpeakerProfile(
            id=data["id"],
            name=data["name"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            num_enrollment_samples=data["num_enrollment_samples"],
            embedding_backend=data["embedding_backend"],
            embedding_dim=len(data["embedding"]),
        )

    def get(self, profile_id: str) -> Optional[SpeakerProfile]:
        data = self._read(profile_id)
        return self._to_profile(data) if data else None

    def list(self) -> list[SpeakerProfile]:
        profiles = []
        for fname in sorted(os.listdir(self._dir)):
            if fname.endswith(".json"):
                data = self._read(fname[: -len(".json")])
                if data:
                    profiles.append(self._to_profile(data))
        return profiles

    def delete(self, profile_id: str) -> bool:
        with self._lock:
            try:
                path = self._file(profile_id)
            except ValueError:
                return False
            if not os.path.exists(path):
                return False
            os.remove(path)
            return True

    def _load_embedding(self, profile_id: str) -> Optional[np.ndarray]:
        data = self._read(profile_id)
        return np.asarray(data["embedding"], dtype=np.float32) if data else None

    def all_embeddings(self) -> list[tuple[str, np.ndarray]]:
        result = []
        for fname in sorted(os.listdir(self._dir)):
            if fname.endswith(".json"):
                profile_id = fname[: -len(".json")]
                emb = self._load_embedding(profile_id)
                if emb is not None:
                    result.append((profile_id, emb))
        return result


def build_store(settings: EnrollmentStoreSettings) -> SpeakerProfileStore:
    if settings.backend == "file":
        return FileSpeakerProfileStore(settings.path)
    raise ValueError(f"Unknown enrollment store backend: {settings.backend}")
