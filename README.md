# Upload Integrity Check (offline)

A small service for government scheme platforms. When a citizen uploads a
file (a flood-damage photo, a marksheet, a certificate), it flags two things
for the officer:

1. **AI influence in the file's metadata.** The file says it was made or
   edited with AI, either through a digitally signed content credential
   (C2PA, added by ChatGPT, Gemini, Adobe Firefly and others) or through
   tool names in its metadata (EXIF / XMP / PNG / PDF).
2. **The same image was already uploaded by another applicant.** For example,
   one flood photo submitted in 13 different applications, even if resized,
   re-compressed or forwarded on WhatsApp.

Each file gets a level and a short note:

| Level | Meaning |
|---|---|
| **high** | Strong evidence: signed AI credential, or same file or photo as another applicant |
| **review** | Worth a look: AI tool named in unsigned metadata, very similar photo, broken credential |
| **none** | No issues found |

> **This is an indicator for human review, not proof.** Missing metadata
> does not prove a file is genuine. See [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## How the scheme platform uses it

The platform calls `POST /api/v1/check` for every upload, sending
`application_id`, `applicant_id` and the file, and stores the returned
`level` and `note` with the application. See **[docs/API.md](docs/API.md)**.

Officers can also check files by hand in the web page (login required).
Admins see a searchable audit log of every check.

## How it works

| Check | How | Code |
|---|---|---|
| File safety | size limit, real type from content (not extension), ClamAV if available, zip/image bomb limits | `app/pipeline/validate.py` |
| AI credential | C2PA reader (offline; remote fetching disabled); signature must be intact | `app/pipeline/provenance.py` |
| AI / editing metadata | EXIF Software, XMP (incl. IPTC "trainedAlgorithmicMedia"), PNG text chunks from Stable Diffusion tools, PDF/DOCX producer | `app/pipeline/provenance.py` |
| Same file | SHA-256 of the file compared with all earlier uploads | `app/pipeline/duplicates.py` |
| Same photo | 64-bit perceptual fingerprint; survives resizing, compression and light cropping | `app/pipeline/fingerprint.py` |
| Flags and note | levels, plain-language messages | `app/pipeline/flags.py`, `app/pipeline/check.py` |

**Photos and documents are treated differently.** Two different students'
marksheets with the same printed layout look alike to a visual fingerprint,
so documents are only matched as **exact** files. Photos are matched
visually. The platform tells the service which kind each upload is
(`doc_type`), or the service guesses.

Uploads by the **same applicant** never flag each other (re-submitting is normal).

## Run locally

Needs Python 3.11 and `libmagic` (`apt install libmagic1`). Any office PC is
enough (about 200 MB RAM).

```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt -c requirements.lock
export BOOTSTRAP_ADMIN_PASSWORD='Choose-a-pass-1'
export API_KEYS='a-long-random-key-for-testing-123'
uvicorn app.main:app --reload       # http://localhost:8000  (user: admin)
```

Tests (network blocked during tests):

```bash
pytest
ruff check . && ruff format --check .
```

## Production (State Data Centre)

See **[docs/SDC_DEPLOYMENT.md](docs/SDC_DEPLOYMENT.md)**:
`./scripts/package_offline.sh` → copy one `.tar` → `verify_bundle.py` →
`install_sdc.sh`. The stack is Docker Compose with Nginx (HTTPS), the app,
PostgreSQL and optional ClamAV. There is no internet access at runtime.

## Security and governance
* Officer/admin login (Argon2id, lockout, forced password change); pluggable LDAP.
* API keys for the platform; keys are never written to logs.
* Audit log of every check: who or which API key, application, applicant,
  SHA-256, flags. **File contents are not stored**; only hashes are kept for
  duplicate matching.
* CSRF protection, strict cookies, Content-Security-Policy, rate limits, secrets in `.env`.

## Earlier version with AI detector models

The first version also ran local AI models (image and text detectors,
Binoculars, language check). It was set aside to keep deployment simple.
It is preserved on the branch **`archive/full-ml-detector`**:

```bash
git checkout archive/full-ml-detector    # look at it or run it
```

Ask to bring it back, or to merge selected parts (e.g. the AI-image model)
into this version.
