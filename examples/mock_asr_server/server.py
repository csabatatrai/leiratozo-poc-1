"""Minimal OpenAI-Whisper-API-compatible mock ASR endpoint.

Lets you run the whole worker (docker compose up) and hit /v1/transcribe
end-to-end WITHOUT a real GPU or model — useful for local dev, CI smoke
tests, and demoing the pipeline. Swap this for any real endpoint
(openai/whisper-large-v3, Groq, faster-whisper-server, ...) by changing
ASR_ENDPOINT_URL — nothing else in the worker changes.

Not part of the worker image; it's a standalone throwaway service.
"""
import io
import wave

from fastapi import FastAPI, Form, UploadFile
from fastapi.responses import JSONResponse

app = FastAPI(title="mock-asr-endpoint")


def _wav_duration_seconds(raw: bytes) -> float:
    try:
        with wave.open(io.BytesIO(raw), "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return 0.0


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile,
    model: str = Form("mock-model"),
    language: str | None = Form(None),
    response_format: str = Form("json"),
):
    audio_bytes = await file.read()
    duration = _wav_duration_seconds(audio_bytes)
    # Fake but deterministic-ish "transcript": just reports what it received,
    # so you can visually confirm segments/speakers routed correctly.
    fake_text = f"[mock transcript, {duration:.1f}s of audio, model={model}]"

    if response_format == "verbose_json":
        return JSONResponse(
            {
                "text": fake_text,
                "language": language or "en",
                "duration": duration,
                "segments": [
                    {
                        "id": 0,
                        "start": 0.0,
                        "end": duration,
                        "text": fake_text,
                        "avg_logprob": -0.2,
                    }
                ],
                "words": [],
            }
        )
    return JSONResponse({"text": fake_text})


@app.get("/v1/health")
async def health():
    return {"status": "ok"}
