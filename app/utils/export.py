"""Export a Transcript to standard subtitle formats (SRT/WebVTT) so any
existing player/editor tooling can consume it without knowing our JSON
schema."""
from __future__ import annotations

from app.schemas import Transcript, TranscriptSegment


def _cue_text(segment: TranscriptSegment) -> str:
    who = segment.speaker.display_name or segment.speaker.id
    return f"[{who}] {segment.text}"


def _srt_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _vtt_timestamp(seconds: float) -> str:
    return _srt_timestamp(seconds).replace(",", ".")


def to_srt(transcript: Transcript) -> str:
    lines = []
    for i, seg in enumerate(transcript.segments, start=1):
        lines.append(str(i))
        lines.append(f"{_srt_timestamp(seg.start)} --> {_srt_timestamp(seg.end)}")
        lines.append(_cue_text(seg))
        lines.append("")
    return "\n".join(lines)


def to_vtt(transcript: Transcript) -> str:
    lines = ["WEBVTT", ""]
    for seg in transcript.segments:
        lines.append(f"{_vtt_timestamp(seg.start)} --> {_vtt_timestamp(seg.end)}")
        lines.append(_cue_text(seg))
        lines.append("")
    return "\n".join(lines)
