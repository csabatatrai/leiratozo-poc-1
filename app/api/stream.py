"""Live transcription over a WebSocket.

Wire protocol (kept intentionally minimal — no negotiation handshake):
client sends binary frames of raw 16-bit signed PCM, mono, 16kHz (see
app.utils.audio.TARGET_SAMPLE_RATE); server pushes back JSON-encoded
StreamEvent messages as they become available. Any text frame received
is ignored (reserved for a future control-message handshake).
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.streaming_pipeline import StreamingSession
from app.schemas import StreamEvent, StreamEventType

router = APIRouter(tags=["stream"])
logger = logging.getLogger("meeting-speaker-adaptation.stream")


@router.websocket("/transcribe/stream")
async def transcribe_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    state = websocket.app.state
    audio_id = str(uuid.uuid4())
    session = StreamingSession(
        audio_id=audio_id,
        settings=state.settings,
        vad=state.vad,
        diarizer=state.diarizer,
        embedder=state.embedder,
        asr_client=state.asr_client,
        store=state.speaker_store,
    )

    await websocket.send_json(StreamEvent(type=StreamEventType.ready, audio_id=audio_id).model_dump(mode="json"))

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            data = message.get("bytes")
            if data is None:
                continue  # ignore text/control frames for now
            async for event in session.push_chunk(data):
                await websocket.send_json(event.model_dump(mode="json"))
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("streaming session %s crashed", audio_id)
    finally:
        try:
            async for event in session.flush():
                await websocket.send_json(event.model_dump(mode="json"))
        except Exception:
            pass  # socket is likely already closed
