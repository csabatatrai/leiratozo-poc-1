from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, speakers, stream, transcribe
from app.config import get_settings
from app.core.asr.factory import build_asr_client
from app.core.diarization import build_diarizer
from app.core.embedding import build_embedder
from app.core.enrollment.store import build_store
from app.core.vad import build_vad
from app.observability import REQUEST_COUNTER, configure_logging, metrics_response

SERVICE_NAME = "meeting-speaker-adaptation"
SERVICE_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger = configure_logging(settings.log_level)
    app.state.settings = settings

    logger.info(
        "loading backends: asr=%s(%s) diarization=%s(%s) embedding=%s(%s) vad=%s",
        settings.asr.backend, settings.asr.model,
        settings.diarization.backend, settings.diarization.model,
        settings.embedding.backend, settings.embedding.model,
        settings.vad.backend,
    )
    app.state.vad = build_vad(settings.vad)
    app.state.diarizer = build_diarizer(settings.diarization)
    app.state.embedder = build_embedder(settings.embedding)
    app.state.asr_client = build_asr_client(settings.asr)
    app.state.speaker_store = build_store(settings.enrollment_store)
    logger.info("startup complete, all backends loaded")

    yield

    await app.state.asr_client.aclose()
    logger.info("shutdown complete")


app = FastAPI(title=SERVICE_NAME, version=SERVICE_VERSION, lifespan=lifespan)

# Permissive by default so this worker is trivially embeddable behind any
# consumer during development; lock this down (specific origins) per
# deployment via a reverse proxy or by editing this list directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/v1")
app.include_router(transcribe.router, prefix="/v1")
app.include_router(stream.router, prefix="/v1")
app.include_router(speakers.router, prefix="/v1")


@app.middleware("http")
async def _metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    REQUEST_COUNTER.labels(route=request.url.path, method=request.method, status=response.status_code).inc()
    logging.getLogger("meeting-speaker-adaptation.http").info(
        "%s %s -> %d (%.1fms)",
        request.method, request.url.path, response.status_code,
        (time.perf_counter() - start) * 1000,
    )
    return response


@app.get("/metrics")
def metrics() -> Response:
    body, content_type = metrics_response()
    return Response(content=body, media_type=content_type)


@app.get("/")
def root() -> dict:
    return {"service": SERVICE_NAME, "version": SERVICE_VERSION, "docs": "/docs"}


if __name__ == "__main__":
    import os

    import uvicorn

    uvicorn.run("app.main:app", host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8000")))
