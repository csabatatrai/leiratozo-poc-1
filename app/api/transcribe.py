from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import PlainTextResponse

from app.core.pipeline import run_batch_pipeline
from app.observability import PIPELINE_LATENCY, timed
from app.schemas import Transcript
from app.utils.export import to_srt, to_vtt

router = APIRouter(tags=["transcribe"])
logger = logging.getLogger("meeting-speaker-adaptation.transcribe")


@router.post("/transcribe")
async def transcribe(
    request: Request,
    file: UploadFile = File(...),
    min_speakers: Optional[int] = Query(None),
    max_speakers: Optional[int] = Query(None),
    language: Optional[str] = Query(None),
    format: str = Query("json", pattern="^(json|srt|vtt)$"),
):
    state = request.app.state
    settings = state.settings

    data = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"file exceeds MAX_UPLOAD_MB={settings.max_upload_mb}")

    audio_id = str(uuid.uuid4())
    try:
        with timed(PIPELINE_LATENCY, mode="batch"):
            transcript: Transcript = await run_batch_pipeline(
                data,
                audio_id,
                settings=settings,
                vad=state.vad,
                diarizer=state.diarizer,
                embedder=state.embedder,
                asr_client=state.asr_client,
                store=state.speaker_store,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
                language=language,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info(
        "batch transcribe done audio_id=%s duration=%.2fs segments=%d speakers=%d",
        audio_id,
        transcript.duration_seconds or 0.0,
        len(transcript.segments),
        len(transcript.speakers),
    )

    if format == "srt":
        return PlainTextResponse(to_srt(transcript), media_type="application/x-subrip")
    if format == "vtt":
        return PlainTextResponse(to_vtt(transcript), media_type="text/vtt")
    return transcript
