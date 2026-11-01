# AI Content Indicator - application image.
# Built on an internet-connected machine by scripts/package_offline.sh.
# Models are NOT baked in; they are mounted read-only from ./models.

ARG PYTHON_IMAGE=python:3.11-slim-bookworm
FROM ${PYTHON_IMAGE}

# CPU build by default. For NVIDIA GPUs build with:
#   --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu126
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_DATASETS_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    DO_NOT_TRACK=1 \
    MODELS_DIR=/models \
    UPLOAD_DIR=/data/uploads \
    HF_HOME=/tmp/hf

# libmagic: file-type detection. exiftool: richer metadata (optional, used if present).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libmagic1 libimage-exiftool-perl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt requirements.lock ./
# Optional: behind a TLS-inspecting proxy, pass its CA certificate with
#   docker build --secret id=ca_bundle,src=/path/to/ca.pem ...
RUN --mount=type=secret,id=ca_bundle,required=false \
    if [ -f /run/secrets/ca_bundle ]; then export PIP_CERT=/run/secrets/ca_bundle; fi \
 && TORCH_VERSION=$(grep -i '^torch==' requirements.lock | cut -d= -f3 | cut -d+ -f1) \
 && pip install "torch==${TORCH_VERSION}" --index-url "${TORCH_INDEX_URL}" \
 && grep -v '^torch==' requirements.lock > /tmp/constraints.txt \
 && pip install -r requirements.txt -c /tmp/constraints.txt

COPY app ./app

RUN useradd --system --uid 10001 --home /srv appuser \
 && mkdir -p /data/uploads /models \
 && chown -R appuser /data
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"

# One worker: models are loaded once (~8 GB RAM with Binoculars).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--workers", "1"]
