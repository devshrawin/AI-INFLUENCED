# API for the scheme platform

The scheme platform calls this service **once for every file a citizen
uploads**. The service answers with a flag level and a short note, which the
platform stores with the application and shows to the officer.

## Request

```
POST https://<server>/api/v1/check
Header:  X-API-Key: <key>            (API_KEYS in .env on the server)
Body:    multipart/form-data
```

| Field | Required | Example | Meaning |
|---|---|---|---|
| `file` | yes | `damage1.jpg` | PDF, DOCX, JPG, PNG or WEBP, max 25 MB |
| `application_id` | yes | `KL-FR-2026-00412` | your application number |
| `applicant_id` | yes | `CIT-889231` | a stable ID for the citizen. Uploads by the **same** applicant never flag each other |
| `scheme` | no | `Flood relief 2026` | shown to officers |
| `doc_type` | no | `photo` | `photo`, `document` or `auto` (default). **Please send it**: you know which upload field the file came from |

Send `photo` for damage, house, crop and site photos, and `document` for
marksheets, certificates and ID cards. With `auto` the service guesses.

**Send the original file.** If the platform resizes or compresses images
before calling this API, their metadata (AI credentials, camera data) is lost.

### Example (curl)

```bash
curl -H "X-API-Key: $KEY" \
     -F application_id=KL-FR-2026-00412 -F applicant_id=CIT-889231 \
     -F "scheme=Flood relief 2026" -F doc_type=photo \
     -F file=@damage1.jpg \
     https://integrity.dept.local/api/v1/check
```

## Response (200)

```json
{
  "application_id": "KL-FR-2026-00977",
  "applicant_id": "CIT-120455",
  "scheme": "Flood relief 2026",
  "filename": "damage1.jpg",
  "sha256": "9f2c…",
  "file_type": "jpeg",
  "treated_as": "photo",
  "size": 183422,
  "level": "high",
  "note": "Flagged: please review before approving.\n- The same photo (possibly resized, compressed or cropped) was already uploaded in 1 other application by a different applicant: KL-FR-2026-00412.\nThis is an indicator for human review, not proof.",
  "flags": [
    {
      "code": "DUPLICATE_PHOTO",
      "level": "high",
      "message": "The same photo (possibly resized, compressed or cropped) was already uploaded in 1 other application by a different applicant: KL-FR-2026-00412.",
      "target": "file",
      "matches": [
        {"application_id": "KL-FR-2026-00412", "applicant_id": "CIT-889231", "scheme": "Flood relief 2026",
         "file_name": "IMG_2231.jpg", "uploaded_at": "2026-11-01 10:01", "distance": 4}
      ]
    }
  ],
  "warnings": [],
  "av_status": "clean",
  "duration_s": 0.12,
  "disclaimer": "This is an indicator for human review, not proof."
}
```

Use **`level`** to decide what to show, and **`note`** as the text for the officer.

| `level` | Show the officer |
|---|---|
| `high` | Red flag: strong evidence, review before approving |
| `review` | Amber flag: worth a look |
| `none` | Nothing |

### Flag codes

| Code | Level | Meaning |
|---|---|---|
| `AI_CREDENTIAL` | high | Digitally signed content credential (C2PA) says the image was made or edited with generative AI (e.g. ChatGPT, Gemini, Firefly) |
| `DUPLICATE_FILE` | high | Exactly the same file was uploaded by another applicant |
| `DUPLICATE_PHOTO` | high | Same photo (resized, compressed or lightly cropped) uploaded by another applicant |
| `SIMILAR_PHOTO` | review | Very similar photo uploaded by another applicant |
| `AI_METADATA` | review | Unsigned metadata names an AI tool (e.g. "Software: Midjourney", IPTC "trainedAlgorithmicMedia") |
| `AI_CREDENTIAL_BROKEN`, `CREDENTIAL_BROKEN` | review | Content credential present but its signature no longer matches the file |
| `EDITING_SOFTWARE` | info | Saved by editing software (Photoshop, Canva, PicsArt…). Shown, never raises the level |
| `CREDENTIAL_OK` | info | Signed credential with no AI declared |

New codes may be added later. Treat unknown codes by their `level`.

## Errors

| Status | Body | Meaning |
|---|---|---|
| 401 | `{"error": "Missing or invalid API key."}` | wrong or missing `X-API-Key` |
| 422 | `{"error": "..."}` | missing field, bad `doc_type`, or file rejected (wrong type, too large, damaged, virus) |
| 429 | `{"error": "Rate limit exceeded."}` | more than `API_RATE_LIMIT` calls per minute per key |

Health check: `GET /api/v1/health` returns `{"status": "ok"}`.

## Notes for platform developers
* Calls are **idempotent per application**: sending the same file again for
  the same application does not create a duplicate record.
* Every call is recorded in the audit log (API key name, application,
  applicant, file hash, flags). File contents are not stored.
* Only fingerprints (hashes) of earlier uploads are kept for comparison,
  never the images.
* Typical response time: 0.1–0.6 s per file.
