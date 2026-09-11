"""Speaker diarization backends — split a mixed-audio buffer into
per-anonymous-speaker turns. Local speaker ids (SPEAKER_00, ...) are only
meaningful within a single call; matching them to real people happens
downstream via app.core.embedding + app.core.enrollment."""
from __future__ import annotations

from typing import Optional

import numpy as np

from app.config import DiarizationSettings
from app.core.interfaces import DiarizedSegment, Diarizer


class PyannoteDiarizer(Diarizer):
    def __init__(self, settings: DiarizationSettings):
        self.settings = settings
        self._pipeline = None

    def _load(self):
        if self._pipeline is None:
            import torch
            from pyannote.audio import Pipeline

            pipeline = Pipeline.from_pretrained(
                self.settings.model, use_auth_token=self.settings.hf_token
            )
            self._pipeline = pipeline.to(torch.device(self.settings.device))
        return self._pipeline

    def diarize(
        self,
        audio: np.ndarray,
        sample_rate: int,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None,
    ) -> list[DiarizedSegment]:
        import torch

        pipeline = self._load()

        waveform = torch.from_numpy(audio.astype(np.float32)).unsqueeze(0)
        pipeline_input = {"waveform": waveform, "sample_rate": sample_rate}

        kwargs = {}
        min_s = min_speakers if min_speakers is not None else self.settings.min_speakers
        max_s = max_speakers if max_speakers is not None else self.settings.max_speakers
        if min_s is not None:
            kwargs["min_speakers"] = min_s
        if max_s is not None:
            kwargs["max_speakers"] = max_s

        diarization = pipeline(pipeline_input, **kwargs)

        # normalize pyannote's raw labels to a stable SPEAKER_NN scheme,
        # ordered by first appearance, independent of pyannote's own label text
        label_order: dict[str, str] = {}
        segments: list[DiarizedSegment] = []
        for turn, _, raw_label in diarization.itertracks(yield_label=True):
            if raw_label not in label_order:
                label_order[raw_label] = f"SPEAKER_{len(label_order):02d}"
            segments.append(
                DiarizedSegment(
                    start=turn.start, end=turn.end, speaker_id=label_order[raw_label]
                )
            )

        return sorted(segments, key=lambda seg: seg.start)


class NoOpDiarizer(Diarizer):
    def diarize(
        self,
        audio: np.ndarray,
        sample_rate: int,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = None,
    ) -> list[DiarizedSegment]:
        return [
            DiarizedSegment(
                start=0.0, end=len(audio) / float(sample_rate), speaker_id="SPEAKER_00"
            )
        ]


def build_diarizer(settings: DiarizationSettings) -> Diarizer:
    if settings.backend == "pyannote":
        return PyannoteDiarizer(settings)
    if settings.backend == "none":
        return NoOpDiarizer()
    raise ValueError(f"Unknown diarization backend: {settings.backend!r}")
