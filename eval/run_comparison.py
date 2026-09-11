#!/usr/bin/env python3
"""Compare "just the raw ASR endpoint" against "our full pipeline"
(VAD -> diarization -> embedding -> enrollment-match -> ASR -> merge),
in batch mode and/or a simulated real-time live mode, on the same audio.

Purpose: give a concrete, repeatable answer to "did the pipeline actually
improve transcription quality AND speaker separation, and does that hold
up in live mode too, not just on a recording?" — see
docs/manual_test_notes.md section 0 for what test data this needs
(minimum recording length / number of distinct speakers).

Usage:
    python -m eval.run_comparison --audio meeting.wav --ground-truth truth.json
    python -m eval.run_comparison --audio meeting.wav --ground-truth truth.json --mode live
    python -m eval.run_comparison --audio meeting.wav   # no ground truth: qualitative diff only

Ground-truth JSON schema (matches meeting-audio-forge's output, ld. README):
    {"speakers": ["Alice", "Bob"],
     "turns": [{"speaker": "Alice", "text": "...", "start": 0.0, "end": 4.2}, ...]}

All pipeline behavior (which diarization/embedding/ASR backend, HF tokens,
similarity threshold, ...) comes from the normal env-var configuration
(app.config.get_settings()) — this script does not reimplement any of
that, it only decides WHICH systems to run and HOW to score them.
"""
from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import sys
import time
from dataclasses import asdict, dataclass
from typing import Optional

from app.config import get_settings
from app.core.asr.factory import build_asr_client
from app.core.diarization import build_diarizer
from app.core.embedding import build_embedder
from app.core.enrollment.store import build_store
from app.core.pipeline import run_batch_pipeline
from app.core.streaming_pipeline import StreamingSession
from app.core.vad import build_vad
from app.schemas import Transcript, TranscriptSegment
from app.utils.audio import TARGET_SAMPLE_RATE, decode_bytes, load_audio_file
from eval.ground_truth import GroundTruth, load_ground_truth
from eval.metrics import char_error_rate, speaker_attribution_accuracy, word_error_rate


@dataclass
class SystemResult:
    name: str
    text: str
    segments: list  # objects with .start .end .speaker.id/.is_enrolled/.display_name
    elapsed_seconds: float
    wer: Optional[float] = None
    cer: Optional[float] = None
    speaker_accuracy: Optional[float] = None
    speaker_mapping: Optional[dict] = None
    num_predicted_speakers: int = 0


def _segments_text(segments) -> str:
    return " ".join(s.text for s in sorted(segments, key=lambda s: s.start))


async def run_baseline(audio_bytes: bytes, settings, language: Optional[str]) -> SystemResult:
    """"Just the endpoint": one whole-file ASR call, zero diarization/VAD/embedding."""
    audio, sr = decode_bytes(audio_bytes)
    asr_client = build_asr_client(settings.asr)
    t0 = time.time()
    result = await asr_client.transcribe(audio, sr, language=language)
    elapsed = time.time() - t0
    await asr_client.aclose()

    # Represent "no diarization" as a single undivided speaker turn spanning
    # the whole clip — the fair way to score "this system gives zero speaker
    # information" against a multi-speaker ground truth.
    from app.schemas import SpeakerLabel

    duration = len(audio) / float(sr)
    fake_segment = TranscriptSegment(
        start=0.0, end=duration, speaker=SpeakerLabel(id="SPEAKER_00"), text=result.text
    )
    return SystemResult(
        name="baseline (csak a végpont)",
        text=result.text,
        segments=[fake_segment],
        elapsed_seconds=elapsed,
        num_predicted_speakers=1,
    )


async def run_pipeline_batch(audio_bytes: bytes, settings, language: Optional[str]) -> SystemResult:
    vad = build_vad(settings.vad)
    diarizer = build_diarizer(settings.diarization)
    embedder = build_embedder(settings.embedding)
    asr_client = build_asr_client(settings.asr)
    store = build_store(settings.enrollment_store)

    t0 = time.time()
    transcript: Transcript = await run_batch_pipeline(
        audio_bytes, "eval-batch",
        settings=settings, vad=vad, diarizer=diarizer,
        embedder=embedder, asr_client=asr_client, store=store,
        language=language,
    )
    elapsed = time.time() - t0
    await asr_client.aclose()

    return SystemResult(
        name="pipeline (batch)",
        text=_segments_text(transcript.segments),
        segments=transcript.segments,
        elapsed_seconds=elapsed,
        num_predicted_speakers=len(transcript.speakers),
    )


async def run_pipeline_live(
    audio_bytes: bytes, settings, language: Optional[str], *, chunk_ms: int, realtime: bool
) -> SystemResult:
    """Simulates real-time arrival by feeding fixed-size PCM16 chunks
    through the same StreamingSession the WS endpoint uses. With
    --realtime, sleeps between chunks so elapsed_seconds reflects true
    wall-clock latency, not just processing time."""
    vad = build_vad(settings.vad)
    diarizer = build_diarizer(settings.diarization)
    embedder = build_embedder(settings.embedding)
    asr_client = build_asr_client(settings.asr)
    store = build_store(settings.enrollment_store)

    audio, sr = decode_bytes(audio_bytes)
    assert sr == TARGET_SAMPLE_RATE
    pcm16 = (audio * 32768.0).clip(-32768, 32767).astype("int16").tobytes()
    chunk_samples = int(sr * chunk_ms / 1000)
    chunk_bytes = chunk_samples * 2  # int16

    session = StreamingSession(
        audio_id="eval-live", settings=settings, vad=vad, diarizer=diarizer,
        embedder=embedder, asr_client=asr_client, store=store,
    )

    final_segments: list[TranscriptSegment] = []
    t0 = time.time()
    for i in range(0, len(pcm16), chunk_bytes):
        chunk = pcm16[i : i + chunk_bytes]
        async for event in session.push_chunk(chunk):
            if event.type.value == "final_segment" and event.segment:
                final_segments.append(event.segment)
        if realtime:
            await asyncio.sleep(chunk_ms / 1000.0)
    async for event in session.flush():
        if event.type.value == "final_segment" and event.segment:
            final_segments.append(event.segment)
    elapsed = time.time() - t0
    await asr_client.aclose()

    speakers = {s.speaker.id for s in final_segments}
    return SystemResult(
        name="pipeline (élő/streaming, szimulált)",
        text=_segments_text(final_segments),
        segments=final_segments,
        elapsed_seconds=elapsed,
        num_predicted_speakers=len(speakers),
    )


def score_against_ground_truth(result: SystemResult, gt: GroundTruth) -> None:
    result.wer = word_error_rate(gt.full_text, result.text)
    result.cer = char_error_rate(gt.full_text, result.text)
    attribution = speaker_attribution_accuracy(gt.turns, result.segments)
    result.speaker_accuracy = attribution.accuracy
    result.speaker_mapping = attribution.mapping


def print_report(results: list[SystemResult], gt: Optional[GroundTruth]) -> None:
    print("\n=== Összehasonlítás ===\n")
    header = f"{'Rendszer':<32} {'idő (s)':>8} {'beszélők':>9}"
    if gt:
        header += f" {'WER':>8} {'CER':>8} {'beszélő-acc':>12}"
    print(header)
    print("-" * len(header))
    for r in results:
        row = f"{r.name:<32} {r.elapsed_seconds:>8.1f} {r.num_predicted_speakers:>9}"
        if gt:
            wer = f"{r.wer * 100:.1f}%" if r.wer is not None else "n/a"
            cer = f"{r.cer * 100:.1f}%" if r.cer is not None else "n/a"
            acc = f"{r.speaker_accuracy * 100:.1f}%" if r.speaker_accuracy is not None else "n/a"
            row += f" {wer:>8} {cer:>8} {acc:>12}"
        print(row)

    if gt is None and len(results) >= 2:
        print("\nNincs ground truth — csak szöveges diff a baseline és a pipeline-batch között:")
        base = next((r for r in results if r.name.startswith("baseline")), None)
        pipe = next((r for r in results if "batch" in r.name), None)
        if base and pipe:
            diff = difflib.unified_diff(
                base.text.split(), pipe.text.split(), lineterm="", n=3,
                fromfile="baseline", tofile="pipeline_batch",
            )
            print("\n".join(list(diff)[:200]))
    elif gt:
        print("\nBeszélő-hozzárendelés (ref -> predikció) a pipeline-rendszereknél:")
        for r in results:
            if r.speaker_mapping:
                print(f"  {r.name}: {r.speaker_mapping}")


def write_report(results: list[SystemResult], out_path: str) -> None:
    payload = []
    for r in results:
        entry = asdict(r)
        entry["segments"] = [s.model_dump(mode="json") for s in r.segments]
        payload.append(entry)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(f"\nRészletes JSON riport: {out_path}")


async def main_async(args: argparse.Namespace) -> None:
    settings = get_settings()
    with open(args.audio, "rb") as fh:
        audio_bytes = fh.read()

    gt = load_ground_truth(args.ground_truth) if args.ground_truth else None

    results: list[SystemResult] = []

    if args.mode in ("batch", "both"):
        results.append(await run_baseline(audio_bytes, settings, args.language))
        results.append(await run_pipeline_batch(audio_bytes, settings, args.language))
    if args.mode in ("live", "both"):
        # decode once via load_audio_file to make sure the source is a real
        # file ffmpeg can seek/stream from consistently with batch mode
        load_audio_file(args.audio)  # raises early with a clear error if undecodable
        results.append(
            await run_pipeline_live(
                audio_bytes, settings, args.language,
                chunk_ms=args.chunk_ms, realtime=args.realtime,
            )
        )

    if gt:
        for r in results:
            score_against_ground_truth(r, gt)

    print_report(results, gt)
    if args.out:
        write_report(results, args.out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--audio", required=True, help="Bemeneti hangfájl (bármilyen ffmpeg-kompatibilis formátum).")
    parser.add_argument("--ground-truth", help="Referencia JSON (speakers[]/turns[]) — ld. modul docstring.")
    parser.add_argument("--mode", choices=["batch", "live", "both"], default="both")
    parser.add_argument("--language", default=None, help="ISO-639-1 nyelvkód-hint (pl. 'hu'); alapértelmezés: ASR_LANGUAGE.")
    parser.add_argument("--chunk-ms", type=int, default=20, help="Élő módban a szimulált audio-chunk mérete ms-ben.")
    parser.add_argument("--realtime", action="store_true", help="Élő módban valós idejű alvással etesse a chunkokat (latencia-méréshez).")
    parser.add_argument("--out", help="Ha meg van adva, ide írja a részletes JSON riportot.")
    args = parser.parse_args()

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
