# Cloud Run image for Aria (FastAPI + Pipecat).
#
# Pipecat needs a few native libs (libsndfile for audio I/O, ffmpeg for some
# resampling paths used by ElevenLabs/Sarvam services). python:3.12-slim
# keeps the layer thin; we install only what's required.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps for pipecat audio extras.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libsndfile1 \
        ffmpeg \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first for layer caching.
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app ./app
COPY scripts ./scripts

# Cloud Run injects PORT. Default to 8080 for local `docker run`.
ENV PORT=8080
EXPOSE 8080

# Single worker is correct for Pipecat: each call holds a long-lived WS and
# state that should not be split across workers. Concurrency is scaled by
# Cloud Run instances, not threads.
#
# `--proxy-headers` and `--forwarded-allow-ips='*'` let FastAPI see the
# real client IP behind Cloud Run's L7 load balancer (needed for rate limit).
CMD exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --workers 1 \
    --proxy-headers \
    --forwarded-allow-ips='*' \
    --timeout-keep-alive 75
