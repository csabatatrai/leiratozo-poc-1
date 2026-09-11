from __future__ import annotations

from app.config import ASRSettings
from app.core.asr.generic import GenericAsrClient
from app.core.asr.openai_compatible import OpenAICompatibleAsrClient
from app.core.interfaces import AsrClient


def build_asr_client(settings: ASRSettings) -> AsrClient:
    if settings.backend == "openai_compatible":
        return OpenAICompatibleAsrClient(settings)
    if settings.backend == "generic":
        return GenericAsrClient(settings)
    raise ValueError(f"Unknown ASR backend: {settings.backend!r}")
