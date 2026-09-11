"""Central, env-driven configuration. Every pluggable piece of the
pipeline (ASR backend, diarization model, embedding model, VAD, storage)
is selected and tuned here — nothing is hardcoded in the pipeline code.

All settings can be overridden by environment variables (see .env.example)
or a mounted config.yaml (set CONFIG_FILE to its path); env vars win.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal, Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ASRSettings(BaseSettings):
    # "openai_compatible": POSTs multipart/form-data to <url>/audio/transcriptions
    #   exactly like the OpenAI Whisper API — the de-facto standard implemented by
    #   OpenAI itself, Groq, faster-whisper-server, LocalAI, vLLM's audio endpoint, etc.
    #   Point this at ANY server that speaks that dialect and the model behind it
    #   is fully swappable (whisper-large-v3, distil-whisper, whisper.cpp, ...).
    # "generic": fully field-mapped HTTP client for endpoints that don't speak the
    #   OpenAI dialect — see GENERIC_* settings below.
    backend: Literal["openai_compatible", "generic"] = "openai_compatible"
    endpoint_url: str = Field(
        "http://localhost:9000/v1", description="Base URL of the transcription API."
    )
    api_key: Optional[str] = None
    model: str = Field(
        "whisper-large-v3", description="Model name passed through to the ASR endpoint."
    )
    language: Optional[str] = Field(None, description="ISO-639-1 hint, or None for auto-detect.")
    timeout_seconds: float = 120.0
    max_retries: int = 3
    request_concurrency: int = Field(
        4, description="Max in-flight requests to the ASR endpoint (batch segment fan-out)."
    )

    # generic backend field mapping (ignored unless backend == "generic")
    generic_audio_field: str = "file"
    generic_extra_form_fields: dict[str, str] = Field(default_factory=dict)
    generic_response_text_path: str = Field(
        "text", description="Dot-path to the transcript string in the JSON response."
    )
    generic_response_segments_path: Optional[str] = Field(
        None, description="Optional dot-path to a list of {start,end,text} objects."
    )

    model_config = SettingsConfigDict(env_prefix="ASR_")


class VADSettings(BaseSettings):
    backend: Literal["webrtcvad", "silero", "none"] = "webrtcvad"
    aggressiveness: int = Field(2, ge=0, le=3, description="webrtcvad only: 0 (loose) - 3 (strict).")
    min_speech_ms: int = 250
    min_silence_ms: int = 300
    frame_ms: Literal[10, 20, 30] = 30

    model_config = SettingsConfigDict(env_prefix="VAD_")


class DiarizationSettings(BaseSettings):
    # "pyannote": pyannote.audio pretrained pipeline (best quality, needs HF_TOKEN
    #   for gated model weights). "none": skip diarization, whole file = one speaker
    #   (useful for single-speaker recordings or when diarization runs upstream).
    backend: Literal["pyannote", "none"] = "pyannote"
    model: str = "pyannote/speaker-diarization-3.1"
    hf_token: Optional[str] = Field(None, description="HuggingFace token for gated model weights.")
    min_speakers: Optional[int] = None
    max_speakers: Optional[int] = None
    device: Literal["cpu", "cuda"] = "cpu"

    model_config = SettingsConfigDict(env_prefix="DIARIZATION_")


class EmbeddingSettings(BaseSettings):
    # Speaker embedding model used for BOTH (a) telling anonymous diarized
    # speakers apart within one recording and (b) matching against enrolled
    # voice profiles. Swappable independently of the diarization backend.
    backend: Literal["pyannote_embedding", "speechbrain_ecapa"] = "pyannote_embedding"
    model: str = "pyannote/embedding"
    hf_token: Optional[str] = Field(
        None, description="HuggingFace token for gated model weights (pyannote backend)."
    )
    device: Literal["cpu", "cuda"] = "cpu"
    similarity_threshold: float = Field(
        0.75,
        ge=0.0,
        le=1.0,
        description="Min cosine similarity to attribute a segment to an enrolled speaker.",
    )

    model_config = SettingsConfigDict(env_prefix="EMBEDDING_")


class EnrollmentStoreSettings(BaseSettings):
    backend: Literal["file"] = "file"
    path: str = "/data/speaker_profiles"

    model_config = SettingsConfigDict(env_prefix="ENROLLMENT_STORE_")


class StreamingSettings(BaseSettings):
    chunk_ms: int = Field(20, description="Expected size of each incoming audio chunk, in ms.")
    window_seconds: float = Field(
        8.0, description="Rolling buffer window re-diarized/re-transcribed on each flush."
    )
    partial_emit_interval_seconds: float = Field(
        1.5, description="How often to emit partial (unstable) segments while speech is ongoing."
    )
    finalize_after_silence_ms: int = Field(
        600, description="Silence duration that closes/finalizes the current segment."
    )

    model_config = SettingsConfigDict(env_prefix="STREAMING_")


class Settings(BaseSettings):
    log_level: str = "INFO"
    max_upload_mb: int = 500
    tmp_dir: str = "/tmp/meeting-speaker-adaptation"

    asr: ASRSettings = Field(default_factory=ASRSettings)
    vad: VADSettings = Field(default_factory=VADSettings)
    diarization: DiarizationSettings = Field(default_factory=DiarizationSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    enrollment_store: EnrollmentStoreSettings = Field(default_factory=EnrollmentStoreSettings)
    streaming: StreamingSettings = Field(default_factory=StreamingSettings)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def _load_yaml_overrides() -> dict:
    path = os.environ.get("CONFIG_FILE")
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache
def get_settings() -> Settings:
    overrides = _load_yaml_overrides()
    return Settings(**overrides) if overrides else Settings()
