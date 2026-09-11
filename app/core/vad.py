"""Voice-activity detection backends. Heavy deps are imported lazily
inside each class so a deployment using only one backend doesn't need
the others installed."""
from __future__ import annotations

from typing import Optional

import numpy as np

from app.config import VADSettings
from app.core.interfaces import SpeechSegment, VoiceActivityDetector

_WEBRTC_RATES = (8000, 16000, 32000, 48000)


class WebrtcVadAdapter(VoiceActivityDetector):
    def __init__(self, settings: VADSettings):
        self.settings = settings

    def detect(self, audio: np.ndarray, sample_rate: int) -> list[SpeechSegment]:
        import webrtcvad

        if sample_rate not in _WEBRTC_RATES:
            raise ValueError(
                f"webrtcvad only supports {_WEBRTC_RATES} Hz, got {sample_rate} — "
                "the pipeline should always feed app.utils.audio.TARGET_SAMPLE_RATE."
            )

        vad = webrtcvad.Vad(self.settings.aggressiveness)
        frame_len = int(sample_rate * self.settings.frame_ms / 1000)

        pcm16 = np.clip(audio * 32768.0, -32768, 32767).astype(np.int16)

        flags: list[bool] = []
        n_frames = len(pcm16) // frame_len
        for i in range(n_frames):
            frame = pcm16[i * frame_len : (i + 1) * frame_len]
            flags.append(vad.is_speech(frame.tobytes(), sample_rate))

        frame_s = self.settings.frame_ms / 1000.0
        min_speech_s = self.settings.min_speech_ms / 1000.0
        min_silence_s = self.settings.min_silence_ms / 1000.0

        # merge speech frames, bridging short silence gaps
        raw_segments: list[list[float]] = []
        for i, is_speech in enumerate(flags):
            if not is_speech:
                continue
            start = i * frame_s
            end = start + frame_s
            if raw_segments and start - raw_segments[-1][1] <= min_silence_s:
                raw_segments[-1][1] = end
            else:
                raw_segments.append([start, end])

        segments = [
            SpeechSegment(start=s, end=e) for s, e in raw_segments if (e - s) >= min_speech_s
        ]
        return sorted(segments, key=lambda seg: seg.start)


class SileroVadAdapter(VoiceActivityDetector):
    # Uses the `silero-vad` pip package's ready-made `get_speech_timestamps`
    # utility (rather than torch.hub, which re-downloads/JITs the model on
    # every cold start) — it already implements min-speech/min-silence
    # merging so we don't duplicate that logic here.
    def __init__(self, settings: VADSettings):
        self.settings = settings
        self._model = None

    def _load(self):
        if self._model is None:
            from silero_vad import load_silero_vad

            self._model = load_silero_vad()
        return self._model

    def detect(self, audio: np.ndarray, sample_rate: int) -> list[SpeechSegment]:
        import torch
        from silero_vad import get_speech_timestamps

        model = self._load()
        tensor = torch.from_numpy(audio.astype(np.float32))
        timestamps = get_speech_timestamps(
            tensor,
            model,
            sampling_rate=sample_rate,
            min_speech_duration_ms=self.settings.min_speech_ms,
            min_silence_duration_ms=self.settings.min_silence_ms,
            return_seconds=True,
        )
        return [SpeechSegment(start=t["start"], end=t["end"]) for t in timestamps]


class NoOpVad(VoiceActivityDetector):
    def detect(self, audio: np.ndarray, sample_rate: int) -> list[SpeechSegment]:
        return [SpeechSegment(start=0.0, end=len(audio) / float(sample_rate))]


def build_vad(settings: VADSettings) -> VoiceActivityDetector:
    if settings.backend == "webrtcvad":
        return WebrtcVadAdapter(settings)
    if settings.backend == "silero":
        return SileroVadAdapter(settings)
    if settings.backend == "none":
        return NoOpVad()
    raise ValueError(f"Unknown VAD backend: {settings.backend!r}")
