from __future__ import annotations

import asyncio
import re
import uuid

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.schemas import EnrollResponse, SpeakerProfileList
from app.utils.audio import decode_bytes

router = APIRouter(tags=["speakers"])


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or uuid.uuid4().hex[:8]


@router.post("/speakers", response_model=EnrollResponse)
async def enroll_speaker(request: Request, name: str = Form(...), audio: UploadFile = File(...)) -> EnrollResponse:
    state = request.app.state
    data = await audio.read()
    try:
        pcm, sr = decode_bytes(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # reuse an existing profile id for repeat enrollments of the same
    # name (case-insensitive) so voice samples accumulate into one
    # profile instead of creating duplicates.
    existing = next((p for p in state.speaker_store.list() if p.name.lower() == name.lower()), None)
    profile_id = existing.id if existing else _slugify(name)

    embedding = await asyncio.to_thread(state.embedder.embed, pcm, sr)
    state.speaker_store.upsert(profile_id, name, embedding, state.settings.embedding.backend)

    profile = state.speaker_store.get(profile_id)
    return EnrollResponse(profile=profile)


@router.get("/speakers", response_model=SpeakerProfileList)
def list_speakers(request: Request) -> SpeakerProfileList:
    return SpeakerProfileList(speakers=request.app.state.speaker_store.list())


@router.delete("/speakers/{profile_id}", status_code=204)
def delete_speaker(profile_id: str, request: Request) -> None:
    if not request.app.state.speaker_store.delete(profile_id):
        raise HTTPException(status_code=404, detail="speaker profile not found")
