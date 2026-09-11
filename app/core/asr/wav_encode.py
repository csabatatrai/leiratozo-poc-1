"""Local WAV encoding helper, kept private to the asr package so this
module doesn't need to depend on app/utils/audio.py internals."""
from __future__ import annotations

import io
import wave

import numpy as np


def float32_to_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    """Encode mono float32 PCM in [-1, 1] as a 16-bit PCM WAV file."""
    clipped = np.clip(audio, -1.0, 1.0)
    pcm16 = (clipped * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())
    return buf.getvalue()
