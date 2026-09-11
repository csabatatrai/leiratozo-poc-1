"""Batch orchestration: VAD -> diarization -> embedding -> enrollment
match -> ASR -> merge into the standard Transcript contract.

The same per-segment logic (`_transcribe_diarized_segments`) is reused by
`streaming_pipeline.py` for live mode, so batch and live share one code
path for "what happens to a chunk of audio with known speaker turns".
"""
from __future__ import annotations

import asyncio
from collections import Counter
from typing import Optional

import numpy as np

from app.config import Settings
from app.core.enrollment.matcher import match_speaker
from app.core.interfaces import AsrClient, Diarizer, EmbeddingExtractor, SpeakerProfileStore, VoiceActivityDetector
from app.schemas import ModelInfo, SpeakerLabel, Transcript, TranscriptSegment, TranscriptionMode
from app.utils.audio import decode_bytes, slice_seconds


async def _transcribe_diarized_segments(
    audio: np.ndarray,
    sample_rate: int,
    diarized_segments,
    *,
    settings: Settings,
    embedder: EmbeddingExtractor,
    asr_client: AsrClient,
    store: SpeakerProfileStore,
    language: Optional[str],
    time_offset: float = 0.0,
) -> list[TranscriptSegment]:
    """Turn diarizer output for one audio buffer into standard
    TranscriptSegments: embed + enrollment-match each speaker turn, then
    fan the ASR calls out concurrently."""
    if not diarized_segments:
        return []

    clips = [slice_seconds(audio, sample_rate, seg.start, seg.end) for seg in diarized_segments]

    # embed() is a sync CPU/GPU-bound call -> offload to a thread so it
    # never blocks the event loop (and other concurrent requests/streams).
    embeddings = await asyncio.gather(
        *(asyncio.to_thread(embedder.embed, clip, sample_rate) for clip in clips)
    )

    speaker_labels: list[SpeakerLabel] = []
    for seg, embedding in zip(diarized_segments, embeddings):
        match = match_speaker(embedding, store, settings.embedding.similarity_threshold)
        if match:
            enrolled_id, display_name, score = match
            speaker_labels.append(
                SpeakerLabel(
                    id=seg.speaker_id,
                    enrolled_id=enrolled_id,
                    display_name=display_name,
                    is_enrolled=True,
                    confidence=score,
                )
            )
        else:
            speaker_labels.append(SpeakerLabel(id=seg.speaker_id))

    asr_results = await asyncio.gather(
        *(asr_client.transcribe(clip, sample_rate, language=language) for clip in clips)
    )

    segments = []
    for seg, label, asr in zip(diarized_segments, speaker_labels, asr_results):
        segments.append(
            TranscriptSegment(
                start=seg.start + time_offset,
                end=seg.end + time_offset,
                speaker=label,
                text=asr.text,
                language=asr.language,
                words=asr.words,
                asr_confidence=asr.confidence,
                is_final=True,
            )
        )
    return segments


def _dedupe_speakers(segments: list[TranscriptSegment]) -> list[SpeakerLabel]:
    seen: dict[str, SpeakerLabel] = {}
    for seg in segments:
        seen.setdefault(seg.speaker.id, seg.speaker)
    return list(seen.values())


def _majority_language(segments: list[TranscriptSegment], fallback: Optional[str]) -> Optional[str]:
    langs = [s.language for s in segments if s.language]
    if not langs:
        return fallback
    return Counter(langs).most_common(1)[0][0]


async def run_batch_pipeline(
    audio_bytes: bytes,
    audio_id: str,
    *,
    settings: Settings,
    vad: VoiceActivityDetector,
    diarizer: Diarizer,
    embedder: EmbeddingExtractor,
    asr_client: AsrClient,
    store: SpeakerProfileStore,
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
    language: Optional[str] = None,
) -> Transcript:
    audio, sample_rate = decode_bytes(audio_bytes)

    effective_min = min_speakers if min_speakers is not None else settings.diarization.min_speakers
    effective_max = max_speakers if max_speakers is not None else settings.diarization.max_speakers
    effective_language = language if language is not None else settings.asr.language

    # diarize()/detect() are sync CPU/GPU-bound calls -> offload to a
    # thread so the event loop stays free for other concurrent requests.
    if settings.diarization.backend == "none":
        # trim leading/trailing silence with VAD before treating the whole
        # buffer as one speaker turn; pyannote already does this internally.
        speech = await asyncio.to_thread(vad.detect, audio, sample_rate)
        if speech:
            start = min(s.start for s in speech)
            end = max(s.end for s in speech)
        else:
            start, end = 0.0, len(audio) / float(sample_rate)
        diarized = await asyncio.to_thread(diarizer.diarize, audio, sample_rate, effective_min, effective_max)
        # NoOpDiarizer ignores speech bounds; re-clip its single segment to the VAD bounds.
        if len(diarized) == 1:
            diarized[0].start, diarized[0].end = start, end
    else:
        diarized = await asyncio.to_thread(diarizer.diarize, audio, sample_rate, effective_min, effective_max)

    segments = await _transcribe_diarized_segments(
        audio,
        sample_rate,
        diarized,
        settings=settings,
        embedder=embedder,
        asr_client=asr_client,
        store=store,
        language=effective_language,
    )
    segments.sort(key=lambda s: s.start)

    return Transcript(
        audio_id=audio_id,
        mode=TranscriptionMode.batch,
        duration_seconds=len(audio) / float(sample_rate),
        language=_majority_language(segments, effective_language),
        speakers=_dedupe_speakers(segments),
        segments=segments,
        models=ModelInfo(
            asr_backend=settings.asr.backend,
            asr_model=settings.asr.model,
            diarization_backend=settings.diarization.backend,
            diarization_model=settings.diarization.model if settings.diarization.backend != "none" else None,
            embedding_backend=settings.embedding.backend,
            embedding_model=settings.embedding.model,
            vad_backend=settings.vad.backend,
        ),
    )
