"""ASR client for the OpenAI Whisper API request/response dialect — the
de-facto industry standard also implemented by Groq, faster-whisper-server,
LocalAI, vLLM's audio endpoint, and most self-hosted Whisper servers.
Pointing ASR_ENDPOINT_URL at any of these swaps the underlying model with
zero code changes."""
from __future__ import annotations

import asyncio
import math
from typing import Any, Optional

import httpx
import numpy as np

from app.config import ASRSettings
from app.core.asr.wav_encode import float32_to_wav_bytes
from app.core.interfaces import AsrClient, AsrResult

_RETRY_DELAYS = (0.5, 1.0, 2.0)


class OpenAICompatibleAsrClient(AsrClient):
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
        url = f"{self._settings.endpoint_url.rstrip('/')}/audio/transcriptions"
        data: dict[str, Any] = {
            "model": self._settings.model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": "word",
        }
        lang = language or self._settings.language
        if lang:
            data["language"] = lang

        async with self._semaphore:
            payload = await self._post_with_retry(
                url, data=data, files={"file": ("audio.wav", wav_bytes, "audio/wav")}
            )
        return self._parse_response(payload)

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
                    # 4xx = bad request/model/auth — retrying won't help.
                    raise ValueError(
                        f"ASR endpoint rejected request ({resp.status_code}): {resp.text}"
                    )
                last_exc = ValueError(f"ASR endpoint error ({resp.status_code}): {resp.text}")

            if attempt < self._settings.max_retries:
                await asyncio.sleep(_RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)])

        assert last_exc is not None
        raise last_exc

    @staticmethod
    def _parse_response(payload: dict) -> AsrResult:
        text = payload.get("text", "")
        language = payload.get("language")

        confidence = None
        segments = payload.get("segments")
        if segments:
            logprobs = [s["avg_logprob"] for s in segments if "avg_logprob" in s]
            if logprobs:
                confidence = min(1.0, max(0.0, math.exp(sum(logprobs) / len(logprobs))))

        words = None
        raw_words = payload.get("words")
        if raw_words:
            words = [
                {
                    "word": w.get("word", ""),
                    "start": w.get("start", 0.0),
                    "end": w.get("end", 0.0),
                    "confidence": w.get("confidence") or w.get("probability"),
                }
                for w in raw_words
            ]

        return AsrResult(text=text, language=language, confidence=confidence, words=words)

    async def aclose(self) -> None:
        await self._client.aclose()
