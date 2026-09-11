# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

# ffmpeg: universal audio decode (any container/codec -> PCM) used by app/utils/audio.py
# libsndfile1: transitive runtime dep of several audio libs
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

FROM base AS deps
WORKDIR /build
# gcc/python3-dev: webrtcvad (default VAD_BACKEND) compiles a native
# extension on install. Build-only — this stage's apt layer is discarded,
# only the resulting site-packages get copied into the runtime image below.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
# CPU wheels by default (portable, no CUDA base image required). For a GPU
# build: docker build --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu121 .
# and run the resulting image on a host with nvidia-container-toolkit + set
# DIARIZATION_DEVICE=cuda / EMBEDDING_DEVICE=cuda.
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
# Separate layer so `docker build` cache reuse survives app-code-only changes —
# the torch/pyannote/speechbrain install is by far the slowest part of the build.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --extra-index-url "$TORCH_INDEX_URL" -r requirements.txt

FROM base AS runtime
WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home /app app

COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

COPY app ./app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    ENROLLMENT_STORE_PATH=/data/speaker_profiles \
    TMP_DIR=/tmp/meeting-speaker-adaptation \
    HF_HOME=/data/hf-cache

# /data/hf-cache persists downloaded model weights (diarization + embedding)
# across container restarts so a redeploy doesn't re-download multi-GB models.
RUN mkdir -p /data/speaker_profiles /data/hf-cache /tmp/meeting-speaker-adaptation && \
    chown -R app:app /app /data /tmp/meeting-speaker-adaptation

USER app
VOLUME ["/data/speaker_profiles", "/data/hf-cache"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/v1/health" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
