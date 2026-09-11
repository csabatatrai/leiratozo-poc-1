import numpy as np
import pytest

from app.core.enrollment.store import FileSpeakerProfileStore


def test_upsert_averages_repeat_enrollments(tmp_path):
    store = FileSpeakerProfileStore(str(tmp_path))
    v1 = np.array([1.0, 0.0], dtype=np.float32)
    v2 = np.array([0.0, 1.0], dtype=np.float32)

    store.upsert("alice", "Alice", v1, "pyannote_embedding")
    store.upsert("alice", "Alice", v2, "pyannote_embedding")

    profile = store.get("alice")
    assert profile.num_enrollment_samples == 2

    [(pid, emb)] = store.all_embeddings()
    assert pid == "alice"
    assert np.isclose(np.linalg.norm(emb), 1.0)


def test_delete_rejects_path_traversal(tmp_path):
    store = FileSpeakerProfileStore(str(tmp_path))
    store.upsert("bob", "Bob", np.array([1.0, 0.0]), "pyannote_embedding")

    assert store.delete("../../etc/passwd") is False
    assert store.get("../../etc/passwd") is None
    assert store.delete("bob") is True
    assert store.get("bob") is None
