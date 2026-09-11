from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])

_SECRET_FIELDS = {"api_key", "hf_token"}


def _redact(data: dict) -> dict:
    out = {}
    for k, v in data.items():
        if isinstance(v, dict):
            out[k] = _redact(v)
        elif k in _SECRET_FIELDS:
            out[k] = "***" if v else None
        else:
            out[k] = v
    return out


@router.get("/health")
def health() -> dict:
    """Liveness probe: process is up and serving HTTP."""
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request) -> Response:
    """Readiness probe: the heavy model backends have actually finished
    loading. Return 503 until then so a load balancer / k8s rolling
    deploy doesn't route traffic to a worker that isn't ready yet."""
    state = request.app.state
    backends = ("vad", "diarizer", "embedder", "asr_client", "speaker_store")
    missing = [name for name in backends if getattr(state, name, None) is None]
    if missing:
        return JSONResponse(status_code=503, content={"status": "not_ready", "missing": missing})
    return JSONResponse(status_code=200, content={"status": "ready"})


@router.get("/config")
def config(request: Request) -> dict:
    return _redact(request.app.state.settings.model_dump())
