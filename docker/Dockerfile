# Upload Integrity Check - application image.
# Built on an internet-connected machine by scripts/package_offline.sh.

ARG PYTHON_IMAGE=python:3.11-slim-bookworm
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UPLOAD_DIR=/data/uploads

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
 && pip install -r requirements.txt -c requirements.lock

COPY app ./app

RUN useradd --system --uid 10001 --home /srv appuser \
 && mkdir -p /data/uploads \
 && chown -R appuser /data
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=4 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--workers", "2"]
