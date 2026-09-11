"""Fully field-mapped ASR client for endpoints that don't speak the
OpenAI Whisper API dialect (see openai_compatible.py for that one).
Every request/response detail is driven by ASRSettings.generic_* so this
worker can be pointed at literally any HTTP transcription endpoint."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx
import numpy as np

from app.config import ASRSettings
from app.core.asr.wav_encode import float32_to_wav_bytes
from app.core.interfaces import AsrClient, AsrResult

_RETRY_DELAYS = (0.5, 1.0, 2.0)


def _resolve_dot_path(payload: Any, path: str) -> Any:
    node = payload
    for part in path.split("."):
        if isinstance(node, list):
            try:
                idx = int(part)
            except ValueError:
                raise ValueError(f"Path segment {part!r} is not a list index in {path!r}")
            try:
                node = node[idx]
            except IndexError:
                raise ValueError(f"Index {idx} out of range resolving {path!r}")
        elif isinstance(node, dict):
            if part not in node:
                raise ValueError(f"Key {part!r} not found resolving {path!r} in response {payload!r}")
            node = node[part]
        else:
            raise ValueError(f"Cannot descend into {type(node).__name__} at {part!r} resolving {path!r}")
    return node


class GenericAsrClient(AsrClient):
    def __init__(self, settings: ASRSettings):
        self._settings = settings
        self._semaphore = asyncio.Semaphore(settings.request_concurrency)
        headers = {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
        self._client = httpx.AsyncClient(timeout=settings.timeout_seconds, headers=headers)

    async def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int,
        language: Optional[str] = None,
    ) -> AsrResult:
        wav_bytes = float32_to_wav_bytes(audio, sample_rate)
        data = dict(self._settings.generic_extra_form_fields)
        lang = language or self._settings.language
        if lang and "language" not in data:
            data["language"] = lang

        async with self._semaphore:
            payload = await self._post_with_retry(
                self._settings.endpoint_url,
                data=data,
                files={self._settings.generic_audio_field: ("audio.wav", wav_bytes, "audio/wav")},
            )

        text = _resolve_dot_path(payload, self._settings.generic_response_text_path)
        if not isinstance(text, str):
            raise ValueError(
                f"generic_response_text_path resolved to a {type(text).__name__}, expected str"
            )

        # Per-segment timing from generic_response_segments_path is intentionally
        # not re-diarized here — diarization already happened one level up in the
        # pipeline; this client is called once per already-segmented speech clip.
        if self._settings.generic_response_segments_path:
            _resolve_dot_path(payload, self._settings.generic_response_segments_path)

        return AsrResult(text=text, language=payload.get("language") if isinstance(payload, dict) else None)

    async def _post_with_retry(self, url: str, **kwargs) -> dict:
        last_exc: Optional[Exception] = None
        for attempt in range(self._settings.max_retries + 1):
            try:
                resp = await self._client.post(url, **kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
            else:
                if resp.status_code < 400:
                    return resp.json()
                if resp.status_code < 500:
                    raise ValueError(
                        f"ASR endpoint rejected request ({resp.status_code}): {resp.text}"
                    )
                last_exc = ValueError(f"ASR endpoint error ({resp.status_code}): {resp.text}")

            if attempt < self._settings.max_retries:
                await asyncio.sleep(_RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)])

        assert last_exc is not None
        raise last_exc

    async def aclose(self) -> None:
        await self._client.aclose()
