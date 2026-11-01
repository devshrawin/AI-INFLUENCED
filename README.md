# AI Content Indicator (offline)

A web tool for government officers. Upload a **document** (PDF, DOCX, TXT) or an
**image** (JPG, PNG, WEBP) and get a **score from 0 to 100** for how likely the
content is AI-generated, a label, and a short reason.

| Score | Label |
|---|---|
| ≥ 70 | **Likely AI** |
| 30 – 70 | **Not sure** |
| < 30 | **Likely Human** |
| signed AI credential | **AI (provenance-confirmed)** |
| nothing reliable to measure | **Cannot assess** |

The thresholds are configurable in `.env`.

> **This is an indicator for human review, not proof.**
> Please read [docs/LIMITATIONS.md](docs/LIMITATIONS.md) before using results in any decision.

## Fully offline

The tool is built to run inside a State Data Centre with **no internet access**:

* All models run locally. They are downloaded once on an internet machine,
  checksummed, and copied in. At runtime `HF_HUB_OFFLINE=1` and
  `TRANSFORMERS_OFFLINE=1` are forced (see `app/offline.py`).
* No CDN, fonts, analytics or telemetry. CSS/JS are served from `app/static/`.
* The C2PA reader runs with remote manifest fetching and OCSP lookups disabled.
* In Docker the app sits on an `internal` network with no route out.
* The test suite blocks every network socket (`pytest-socket`). Any code
  that tries to connect out makes the tests fail.

## How a file is checked

```
upload ─► validate (size, real type from magic bytes, ClamAV)
        ├─ image ───► provenance (C2PA + EXIF/XMP/PNG text) ─► 2 image models ─────────────┐
        └─ document ► extract text + embedded images + metadata                             │
                      ├─ embedded images ─► provenance ─► 2 image models                    ├─► combine ─► result
                      └─ text ─► language check ─► chunks ─► Binoculars + DeBERTa classifier ┘
```

| Step | What it does | Code |
|---|---|---|
| Validate | size limit, file type from content (not extension), ClamAV if running | `app/pipeline/validate.py` |
| Provenance | signed C2PA credential declaring AI ⇒ "AI (provenance-confirmed)"; EXIF/XMP/PNG hints add a small bonus | `app/pipeline/provenance.py` |
| Image models | `haywoodsloan/ai-image-detector-deploy` (SwinV2, Apache-2.0) + `Ateeqq/ai-vs-human-image-detector` (SigLIP, Apache-2.0) | `app/pipeline/detectors/image.py` |
| Text models | **Binoculars** zero-shot (Qwen2.5-1.5B + Instruct, Apache-2.0) + `desklib/ai-text-detector-v1.01` (DeBERTa-v3, MIT) | `app/pipeline/detectors/text.py` |
| Language | non-English text (Malayalam, Hindi…) gets a warning and is **not** used for the label | `app/pipeline/language.py` |
| Long text | split into ~384-word sections; the most AI-like sections are shown | `app/pipeline/chunking.py` |
| Combine | simple weighted average, every weight shown on screen | `app/pipeline/combine.py` |

## Run locally (development)

Needs Python 3.11, `libmagic` (`apt install libmagic1`), about 12 GB of free disk
and 16 GB of RAM (8 GB is enough with `ENABLE_BINOCULARS=false`).

```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-dev.txt -c requirements.lock

python scripts/download_models.py            # ~8.5 GB, once (internet needed)

export BOOTSTRAP_ADMIN_PASSWORD='Choose-a-pass-1'
uvicorn app.main:app --reload                # http://localhost:8000  (user: admin)
```

The SQLite dev database is created at `data/app.db`.

Tests (no models or internet needed; tests marked `models` use real weights if present):

```bash
pytest            # all tests, network blocked
pytest -m models  # only the real-model tests
ruff check . && ruff format --check .
```

## Production (State Data Centre)

See **[docs/SDC_DEPLOYMENT.md](docs/SDC_DEPLOYMENT.md)**. In short:

1. On an internet machine: `./scripts/package_offline.sh` produces one `.tar`.
2. Copy it into the SDC. Run `scripts/verify_bundle.py`, then `scripts/install_sdc.sh`.
3. The stack runs Nginx (HTTPS), the app, PostgreSQL and optionally ClamAV, under Docker Compose.

## Security and governance

* Login with roles **admin** and **officer**; Argon2id password hashes; lockout
  after 5 failed attempts; forced change of temporary passwords.
* Pluggable login (`AUTH_PROVIDER=local|ldap`; LDAP/SSO hook in `app/auth/providers.py`).
* **Audit log** of every check: user, time, IP, SHA-256, file type, every score,
  model versions and final label. Document text is **never** stored. Admins can
  search, filter and export it to CSV.
* Uploaded files are not kept (`STORE_UPLOADS=false`). If enabled, they are
  deleted after `RETENTION_HOURS` (default 24).
* CSRF tokens, strict same-site cookies, Content-Security-Policy, rate limiting
  (app and Nginx), and all secrets in `.env`.

## Measuring accuracy on your own data

```bash
python eval/evaluate.py /path/to/testset     # testset/real/*, testset/ai/*
python eval/calibrate_binoculars.py /path/to/text_testset
```

The first writes `eval/reports/report.md` with accuracy, precision, recall,
false-positive rate and confusion matrices, reported separately for images
and text.

## Repository layout

```
app/            FastAPI application (pipeline/, detectors/, auth/, db/, api/, templates/, static/)
scripts/        download_models.py, package_offline.sh, verify_bundle.py, install_sdc.sh
eval/           evaluate.py, calibrate_binoculars.py
tests/          unit + web tests, samples/ (small smoke-test files)
docker/         Dockerfile, nginx.conf
docs/           SDC_DEPLOYMENT.md, LIMITATIONS.md
```
