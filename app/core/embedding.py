"""Speaker-embedding extractors. Used both to tell anonymous diarized
speakers apart within one recording and to match against enrolled voice
profiles (app.core.enrollment). Only extraction lives here — similarity
scoring/matching is owned by app.core.enrollment.matcher."""
from __future__ import annotations

import numpy as np

from app.config import EmbeddingSettings
from app.core.interfaces import EmbeddingExtractor


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


class PyannoteEmbeddingExtractor(EmbeddingExtractor):
    def __init__(self, settings: EmbeddingSettings):
        self.settings = settings
        self._inference = None
        self._dimension: int | None = None

    def _load(self):
        if self._inference is None:
            import torch
            from pyannote.audio import Model
            from pyannote.audio.core.inference import Inference

            model = Model.from_pretrained(
                self.settings.model, use_auth_token=self.settings.hf_token
            )
            model.to(torch.device(self.settings.device))
            # window="whole": one embedding for the entire clip, rather than
            # pyannote's default sliding-window per-frame embeddings — we
            # already receive a single-speaker clip from the diarizer.
            self._inference = Inference(model, window="whole")
        return self._inference

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            # dummy 1s forward pass to read the true output size instead of
            # hardcoding a value that could drift with a different --model
            probe = self.embed(np.zeros(16000, dtype=np.float32), 16000)
            self._dimension = int(probe.shape[-1])
        return self._dimension

    def embed(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        import torch

        inference = self._load()
        waveform = torch.from_numpy(audio.astype(np.float32)).unsqueeze(0)
        vector = inference({"waveform": waveform, "sample_rate": sample_rate})
        vector = np.asarray(vector).reshape(-1)
        return _l2_normalize(vector)


class SpeechBrainEcapaExtractor(EmbeddingExtractor):
    # ECAPA-TDNN (speechbrain/spkrec-ecapa-voxceleb) has a fixed, well-known
    # 192-dim output — cheaper than a dummy forward pass to determine it.
    _DIM = 192

    def __init__(self, settings: EmbeddingSettings):
        self.settings = settings
        self._classifier = None

    def _load(self):
        if self._classifier is None:
            from speechbrain.inference.speaker import EncoderClassifier

            self._classifier = EncoderClassifier.from_hparams(
                source=self.settings.model,
                run_opts={"device": self.settings.device},
            )
        return self._classifier

    @property
    def dimension(self) -> int:
        return self._DIM

    def embed(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        import torch

        classifier = self._load()
        tensor = torch.from_numpy(audio.astype(np.float32)).unsqueeze(0)
        embedding = classifier.encode_batch(tensor)
        vector = embedding.squeeze().detach().cpu().numpy().reshape(-1)
        return _l2_normalize(vector)


def build_embedder(settings: EmbeddingSettings) -> EmbeddingExtractor:
    if settings.backend == "pyannote_embedding":
        return PyannoteEmbeddingExtractor(settings)
    if settings.backend == "speechbrain_ecapa":
        return SpeechBrainEcapaExtractor(settings)
    raise ValueError(f"Unknown embedding backend: {settings.backend!r}")
