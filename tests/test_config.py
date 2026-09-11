from app.config import Settings


def test_defaults_load_without_env():
    s = Settings()
    assert s.asr.backend == "openai_compatible"
    assert s.diarization.backend == "pyannote"
    assert s.embedding.similarity_threshold == 0.75


def test_env_override(monkeypatch):
    monkeypatch.setenv("ASR_MODEL", "whisper-large-v3-hu")
    monkeypatch.setenv("EMBEDDING_SIMILARITY_THRESHOLD", "0.9")
    s = Settings()
    assert s.asr.model == "whisper-large-v3-hu"
    assert s.embedding.similarity_threshold == 0.9
