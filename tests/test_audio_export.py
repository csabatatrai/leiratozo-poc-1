import numpy as np

from app.core.asr.wav_encode import float32_to_wav_bytes
from app.core.enrollment.matcher import cosine_similarity
from app.schemas import ModelInfo, SpeakerLabel, Transcript, TranscriptSegment, TranscriptionMode
from app.utils.audio import decode_bytes
from app.utils.export import to_srt, to_vtt


def test_wav_roundtrip_via_ffmpeg():
    tone = (np.sin(2 * np.pi * 440 * np.arange(16000) / 16000)).astype(np.float32)
    wav_bytes = float32_to_wav_bytes(tone, 16000)
    decoded, sr = decode_bytes(wav_bytes)
    assert sr == 16000
    assert abs(len(decoded) - len(tone)) < 10


def test_cosine_similarity_identical_vectors_is_one():
    v = np.array([1.0, 2.0, 3.0])
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-9


def _sample_transcript() -> Transcript:
    return Transcript(
        audio_id="x",
        mode=TranscriptionMode.batch,
        segments=[
            TranscriptSegment(start=0.0, end=1.234, speaker=SpeakerLabel(id="SPEAKER_00", display_name="Alice"), text="hi"),
        ],
        models=ModelInfo(
            asr_backend="openai_compatible", diarization_backend="none",
            embedding_backend="pyannote_embedding", vad_backend="webrtcvad",
        ),
    )


def test_srt_and_vtt_export():
    t = _sample_transcript()
    srt = to_srt(t)
    assert "00:00:00,000 --> 00:00:01,234" in srt
    assert "[Alice] hi" in srt

    vtt = to_vtt(t)
    assert vtt.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:01.234" in vtt
