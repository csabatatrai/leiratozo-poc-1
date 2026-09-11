from app.schemas import (
    ModelInfo,
    SpeakerLabel,
    Transcript,
    TranscriptSegment,
    TranscriptionMode,
)


def test_transcript_roundtrip():
    t = Transcript(
        audio_id="abc123",
        mode=TranscriptionMode.batch,
        duration_seconds=12.3,
        speakers=[SpeakerLabel(id="SPEAKER_00", is_enrolled=False)],
        segments=[
            TranscriptSegment(
                start=0.0,
                end=1.5,
                speaker=SpeakerLabel(id="SPEAKER_00"),
                text="hello world",
            )
        ],
        models=ModelInfo(
            asr_backend="openai_compatible",
            asr_model="whisper-large-v3",
            diarization_backend="pyannote",
            diarization_model="pyannote/speaker-diarization-3.1",
            embedding_backend="pyannote_embedding",
            embedding_model="pyannote/embedding",
            vad_backend="webrtcvad",
        ),
    )
    dumped = t.model_dump_json()
    restored = Transcript.model_validate_json(dumped)
    assert restored.segments[0].text == "hello world"
    assert restored.schema_version == "1.0"
