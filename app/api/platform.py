"""JSON API for the scheme platform (server-to-server).

    POST /api/v1/check
      Header:  X-API-Key: <key from API_KEYS in .env>
      Form:    application_id, applicant_id, scheme (optional),
               doc_type = auto | photo | document (optional), file
      Returns: {"level": "high|review|none", "note": "...", "flags": [...], ...}

The platform should call this once per uploaded file and store the returned
level and note with the application. Every call is written to the audit log.
"""

from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.limiter import limiter
from app.auth.security import client_ip
from app.config import api_key_list, get_settings
from app.db.models import AuditLog
from app.db.session import get_db
from app.pipeline.check import DOC_TYPES, Submission, check_file
from app.pipeline.validate import ValidationError, validate_upload
from app.services.audit import record_check

router = APIRouter(prefix="/api/v1")


def api_client(request: Request) -> str:
    """Check the X-API-Key header. Returns a short, non-secret name for the key."""
    sent = request.headers.get("X-API-Key", "")
    for key in api_key_list(get_settings()):
        if sent and hmac.compare_digest(sent.encode(), key.encode()):
            name = "api:" + hashlib.sha256(key.encode()).hexdigest()[:8]
            request.state.api_client = name
            return name
    raise HTTPException(status_code=401, detail="Missing or invalid API key.")


def _api_rate_limit() -> str:
    return get_settings().api_rate_limit


@router.post("/check")
@limiter.limit(_api_rate_limit)
async def api_check(
    request: Request,
    file: UploadFile = File(...),
    application_id: str = Form(..., max_length=100),
    applicant_id: str = Form(..., max_length=100),
    scheme: str = Form("", max_length=100),
    doc_type: str = Form("auto"),
    client: str = Depends(api_client),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    data = await file.read(settings.max_upload_bytes + 1)
    try:
        if not application_id.strip() or not applicant_id.strip():
            raise ValidationError("application_id and applicant_id are required.")
        if doc_type not in DOC_TYPES:
            raise ValidationError(f"doc_type must be one of {', '.join(DOC_TYPES)}.")
        vf = validate_upload(data, file.filename or "", settings)
    except ValidationError as exc:
        db.add(
            AuditLog(
                event="rejected",
                username=client,
                client_ip=client_ip(request),
                application_id=application_id,
                applicant_id=applicant_id,
                file_name=(file.filename or "")[:255],
                file_size=len(data),
                detail=str(exc)[:500],
            )
        )
        db.commit()
        return JSONResponse({"error": str(exc)}, status_code=422)
    sub = Submission(application_id.strip(), applicant_id.strip(), scheme.strip(), doc_type)
    result = await run_in_threadpool(check_file, vf, sub, db, settings)
    await run_in_threadpool(record_check, db, client, None, client_ip(request), vf, result, settings)
    return result.to_dict()


@router.get("/health")
def api_health():
    return {"status": "ok"}
