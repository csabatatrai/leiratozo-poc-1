"""Audio IO helpers. Any input container/codec ffmpeg understands (wav,
mp3, m4a, ogg/opus, webm from a browser mic, ...) goes in; everything
internal is mono float32 PCM at a fixed sample rate."""
from __future__ import annotations

import subprocess

import numpy as np

TARGET_SAMPLE_RATE = 16000


def load_audio_file(path: str, target_sr: int = TARGET_SAMPLE_RATE) -> tuple[np.ndarray, int]:
    """Decode an arbitrary audio file to mono float32 PCM via ffmpeg."""
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-threads", "0",
        "-i", path,
        "-f", "f32le",
        "-ac", "1",
        "-ar", str(target_sr),
        "-loglevel", "error",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        raise ValueError(f"ffmpeg failed to decode {path!r}: {proc.stderr.decode(errors='replace')}")
    audio = np.frombuffer(proc.stdout, dtype=np.float32)
    return audio, target_sr


def decode_bytes(data: bytes, target_sr: int = TARGET_SAMPLE_RATE) -> tuple[np.ndarray, int]:
    """Decode arbitrary in-memory audio bytes (any container ffmpeg
    supports) to mono float32 PCM, without touching disk."""
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-threads", "0",
        "-i", "pipe:0",
        "-f", "f32le",
        "-ac", "1",
        "-ar", str(target_sr),
        "-loglevel", "error",
        "pipe:1",
    ]
    proc = subprocess.run(cmd, input=data, capture_output=True, check=False)
    if proc.returncode != 0:
        raise ValueError(f"ffmpeg failed to decode input bytes: {proc.stderr.decode(errors='replace')}")
    audio = np.frombuffer(proc.stdout, dtype=np.float32)
    return audio, target_sr


def slice_seconds(audio: np.ndarray, sample_rate: int, start: float, end: float) -> np.ndarray:
    i0 = max(0, int(start * sample_rate))
    i1 = min(len(audio), int(end * sample_rate))
    return audio[i0:i1]


def duration_seconds(audio: np.ndarray, sample_rate: int) -> float:
    return len(audio) / float(sample_rate)


def pcm16_bytes_to_float32(data: bytes) -> np.ndarray:
    """Convert raw 16-bit PCM (the common wire format for live mic
    streaming) to float32 in [-1, 1]."""
    ints = np.frombuffer(data, dtype=np.int16)
    return (ints.astype(np.float32)) / 32768.0
