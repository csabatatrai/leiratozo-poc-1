"""Live/streaming orchestration for one WebSocket connection.

Design: accumulate incoming PCM16 chunks into a rolling float32 buffer.
On every push we re-run VAD over the whole buffer (cheap compared to
diarization/ASR) to see whether the speaker has gone quiet for long
enough to "finalize" everything buffered so far (full diarization +
embedding + enrollment-match + ASR, same as batch mode), or whether the
buffer has simply grown too large without a pause (latency/memory bound)
and must be force-finalized anyway. While speech is ongoing but not yet
finalized, we periodically emit a cheap, diarization-free partial ASR
result on the current tail so a UI has something to show immediately —
this is intentionally simple, not a true incremental streaming-ASR
protocol.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional

import numpy as np

from app.config import Settings
from app.core.interfaces import AsrClient, Diarizer, EmbeddingExtractor, SpeakerProfileStore, VoiceActivityDetector
from app.core.pipeline import _transcribe_diarized_segments
from app.schemas import SpeakerLabel, StreamEvent, StreamEventType, TranscriptSegment
from app.utils.audio import TARGET_SAMPLE_RATE, pcm16_bytes_to_float32


class StreamingSession:
    def __init__(
        self,
        audio_id: str,
        settings: Settings,
        vad: VoiceActivityDetector,
        diarizer: Diarizer,
        embedder: EmbeddingExtractor,
        asr_client: AsrClient,
        store: SpeakerProfileStore,
    ):
        self.audio_id = audio_id
        self.settings = settings
        self.vad = vad
        self.diarizer = diarizer
        self.embedder = embedder
        self.asr_client = asr_client
        self.store = store

        self.sample_rate = TARGET_SAMPLE_RATE
        self._buffer = np.empty(0, dtype=np.float32)
        self._offset_seconds = 0.0  # stream-absolute time of self._buffer[0]
        self._last_partial_at_buffer_duration = 0.0

    def _buffer_duration(self) -> float:
        return len(self._buffer) / float(self.sample_rate)

    async def _finalize_buffer(self) -> list[StreamEvent]:
        if len(self._buffer) == 0:
            return []
        audio = self._buffer
        cfg = self.settings.diarization
        diarized = await asyncio.to_thread(
            self.diarizer.diarize, audio, self.sample_rate, cfg.min_speakers, cfg.max_speakers
        )
        segments = await _transcribe_diarized_segments(
            audio,
            self.sample_rate,
            diarized,
            settings=self.settings,
            embedder=self.embedder,
            asr_client=self.asr_client,
            store=self.store,
            language=self.settings.asr.language,
            time_offset=self._offset_seconds,
        )
        events = [StreamEvent(type=StreamEventType.final_segment, audio_id=self.audio_id, segment=s) for s in segments]

        self._offset_seconds += self._buffer_duration()
        self._buffer = np.empty(0, dtype=np.float32)
        self._last_partial_at_buffer_duration = 0.0
        return events

    async def _maybe_partial(self) -> Optional[StreamEvent]:
        interval = self.settings.streaming.partial_emit_interval_seconds
        if self._buffer_duration() - self._last_partial_at_buffer_duration < interval:
            return None
        speech = await asyncio.to_thread(self.vad.detect, self._buffer, self.sample_rate)
        if not speech:
            return None
        tail = speech[-1]
        clip = self._buffer[int(tail.start * self.sample_rate):]
        if len(clip) == 0:
            return None
        self._last_partial_at_buffer_duration = self._buffer_duration()
        asr = await self.asr_client.transcribe(clip, self.sample_rate, language=self.settings.asr.language)
        segment = TranscriptSegment(
            start=self._offset_seconds + tail.start,
            end=self._offset_seconds + self._buffer_duration(),
            speaker=SpeakerLabel(id="PENDING"),
            text=asr.text,
            language=asr.language,
            asr_confidence=asr.confidence,
            is_final=False,
        )
        return StreamEvent(type=StreamEventType.partial_segment, audio_id=self.audio_id, segment=segment)

    async def push_chunk(self, pcm16_bytes: bytes) -> AsyncIterator[StreamEvent]:
        new_samples = pcm16_bytes_to_float32(pcm16_bytes)
        self._buffer = np.concatenate([self._buffer, new_samples])

        cfg = self.settings.streaming
        speech = await asyncio.to_thread(self.vad.detect, self._buffer, self.sample_rate)

        if not speech:
            # pure silence buffered so far: nothing to finalize, just cap growth
            if self._buffer_duration() >= cfg.window_seconds:
                self._offset_seconds += self._buffer_duration()
                self._buffer = np.empty(0, dtype=np.float32)
            return

        trailing_silence_ms = (self._buffer_duration() - speech[-1].end) * 1000
        force = self._buffer_duration() >= cfg.window_seconds

        if trailing_silence_ms >= cfg.finalize_after_silence_ms or force:
            for event in await self._finalize_buffer():
                yield event
            return

        partial = await self._maybe_partial()
        if partial:
            yield partial

    async def flush(self) -> AsyncIterator[StreamEvent]:
        for event in await self._finalize_buffer():
            yield event
        yield StreamEvent(type=StreamEventType.closed, audio_id=self.audio_id)
