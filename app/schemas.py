"""Standard, versioned data contracts for the worker.

These schemas are the ONLY thing consumers (meeting-recorder, a live meeting
bot, a UI, ...) are allowed to depend on. Internal pipeline/adapter code may
change freely as long as these shapes and SCHEMA_VERSION stay stable
(bumped + documented in README on breaking change).
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


class SpeakerLabel(BaseModel):
    """One speaker as attributed by diarization + (optionally) enrollment."""

    id: str = Field(..., description="Stable id within this transcript, e.g. 'SPEAKER_00'.")
    enrolled_id: Optional[str] = Field(
        None, description="Id of the matching enrolled voice profile, if any."
    )
    display_name: Optional[str] = Field(
        None, description="Human name of the enrolled speaker, if matched."
    )
    is_enrolled: bool = Field(
        False, description="True if this speaker was matched to a registered voice profile."
    )
    confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Cosine-similarity-derived match confidence (0-1)."
    )


class WordTiming(BaseModel):
    word: str
    start: float
    end: float
    confidence: Optional[float] = None


class TranscriptSegment(BaseModel):
    """One diarized+transcribed utterance. Timestamps are seconds from
    the start of the audio (batch) or from the start of the stream (live)."""

    start: float
    end: float
    speaker: SpeakerLabel
    text: str
    language: Optional[str] = None
    words: Optional[list[WordTiming]] = None
    asr_confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Mean token/logprob-derived confidence from the ASR backend, if provided."
    )
    is_final: bool = Field(
        True, description="False for live-mode partial segments that may still be revised."
    )


class ModelInfo(BaseModel):
    asr_backend: str
    asr_model: Optional[str] = None
    diarization_backend: str
    diarization_model: Optional[str] = None
    embedding_backend: str
    embedding_model: Optional[str] = None
    vad_backend: str


class TranscriptionMode(str, Enum):
    batch = "batch"
    live = "live"


class Transcript(BaseModel):
    """Top-level standard output — the ONE contract this worker promises."""

    schema_version: str = SCHEMA_VERSION
    audio_id: str
    mode: TranscriptionMode
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_seconds: Optional[float] = None
    language: Optional[str] = None
    speakers: list[SpeakerLabel] = Field(default_factory=list)
    segments: list[TranscriptSegment] = Field(default_factory=list)
    models: ModelInfo


class StreamEventType(str, Enum):
    """Event envelope types on the live WebSocket, modeled after the
    partial/final pattern used by common streaming-ASR APIs (Deepgram,
    AWS Transcribe, OpenAI Realtime) so front-ends can reuse familiar
    handling logic."""

    ready = "ready"
    partial_segment = "partial_segment"
    final_segment = "final_segment"
    speaker_update = "speaker_update"
    error = "error"
    closed = "closed"


class StreamEvent(BaseModel):
    type: StreamEventType
    audio_id: str
    segment: Optional[TranscriptSegment] = None
    message: Optional[str] = None


# --- Speaker enrollment -----------------------------------------------------


class SpeakerProfile(BaseModel):
    id: str
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    num_enrollment_samples: int = 1
    embedding_backend: str
    embedding_dim: int


class SpeakerProfileList(BaseModel):
    speakers: list[SpeakerProfile]


class EnrollResponse(BaseModel):
    profile: SpeakerProfile
    message: str = "enrolled"
