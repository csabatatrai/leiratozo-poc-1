"""Abstract interfaces for every pluggable pipeline stage.

Every concrete backend (pyannote diarization, webrtcvad, speechbrain
embeddings, an OpenAI-compatible ASR client, ...) implements one of these.
The orchestrators in `pipeline.py` / `streaming_pipeline.py` only ever
talk to these interfaces, never to a concrete backend directly — that is
what makes the worker model-agnostic and lets `config.py` swap
implementations purely via settings.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Optional

import numpy as np


@dataclass
class SpeechSegment:
    """A time range containing speech, in seconds, relative to the audio
    buffer passed to the VAD/diarization call."""

    start: float
    end: float


@dataclass
class DiarizedSegment(SpeechSegment):
    speaker_id: str  # anonymous, e.g. "SPEAKER_00" — local to this call only


@dataclass
class AsrResult:
    text: str
    language: Optional[str] = None
    confidence: Optional[float] = None
    words: Optional[list[dict]] = None  # [{"word", "start", "end", "confidence"}]


class VoiceActivityDetector(ABC):
    @abstractmethod
    def detect(self, audio: np.ndarray, sample_rate: int) -> list[SpeechSegment]:
        """Return speech-only regions of a mono float32 PCM buffer."""


class Diarizer(ABC):
    @abstractmethod
    def diarize(
        self,
        audio: np.ndarray,
        sample_rate: int,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None,
    ) -> list[DiarizedSegment]:
        """Split a mono float32 PCM buffer into per-anonymous-speaker segments."""


class EmbeddingExtractor(ABC):
    @property
    @abstractmethod
    def dimension(self) -> int: ...

    @abstractmethod
    def embed(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """Return a single fixed-size embedding vector for a speech clip."""

    def embed_many(self, clips: list[tuple[np.ndarray, int]]) -> list[np.ndarray]:
        return [self.embed(audio, sr) for audio, sr in clips]


class AsrClient(ABC):
    @abstractmethod
    async def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int,
        language: Optional[str] = None,
    ) -> AsrResult:
        """Send one (already-segmented) speech clip to the configured ASR
        endpoint and return its transcript. Must be safe to call
        concurrently (see ASR_REQUEST_CONCURRENCY)."""

    async def aclose(self) -> None:
        return None


class SpeakerProfileStore(ABC):
    """Persistence for enrolled voice profiles. See app/core/enrollment/."""

    @abstractmethod
    def upsert(self, profile_id: str, name: str, embedding: np.ndarray, embedding_backend: str) -> None: ...

    @abstractmethod
    def get(self, profile_id: str): ...

    @abstractmethod
    def list(self): ...

    @abstractmethod
    def delete(self, profile_id: str) -> bool: ...

    @abstractmethod
    def all_embeddings(self) -> list[tuple[str, np.ndarray]]:
        """[(profile_id, embedding)] for matching."""
