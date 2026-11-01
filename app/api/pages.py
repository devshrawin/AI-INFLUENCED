"""Officer pages: manual check form, result, own history."""

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.limiter import limiter
from app.api.templating import render
from app.auth.security import client_ip, current_user, verify_csrf
from app.config import get_settings
from app.db.models import AuditLog, User
from app.db.session import get_db
from app.pipeline.check import DOC_TYPES, Submission, check_file
from app.pipeline.validate import ValidationError, validate_upload
from app.services.audit import record_check

router = APIRouter()


@router.get("/")
def index(request: Request, user: User = Depends(current_user)):
    return render(request, "index.html", user=user)


@router.post("/check", dependencies=[Depends(verify_csrf)])
@limiter.limit(lambda: get_settings().rate_limit)
async def check(
    request: Request,
    file: UploadFile = File(...),
    application_id: str = Form(...),
    applicant_id: str = Form(...),
    scheme: str = Form(""),
    doc_type: str = Form("auto"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    application_id, applicant_id = application_id.strip()[:100], applicant_id.strip()[:100]
    data = await file.read(settings.max_upload_bytes + 1)
    try:
        if not application_id or not applicant_id:
            raise ValidationError("Application number and applicant ID are required.")
        if doc_type not in DOC_TYPES:
            raise ValidationError("Unknown document type.")
        vf = validate_upload(data, file.filename or "", settings)
    except ValidationError as exc:
        db.add(
            AuditLog(
                event="rejected",
                user_id=user.id,
                username=user.username,
                client_ip=client_ip(request),
                application_id=application_id,
                applicant_id=applicant_id,
                file_name=(file.filename or "")[:255],
                file_size=len(data),
                detail=str(exc)[:500],
            )
        )
        db.commit()
        return render(request, "_error.html", {"message": str(exc)}, 400, user=user)
    sub = Submission(application_id, applicant_id, scheme.strip()[:100], doc_type)
    result = await run_in_threadpool(check_file, vf, sub, db, settings)
    await run_in_threadpool(record_check, db, user.username, user, client_ip(request), vf, result, settings)
    return render(request, "_result.html", {"r": result}, user=user)


@router.get("/history")
def history(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.user_id == user.id, AuditLog.event == "check")
        .order_by(AuditLog.created_at.desc())
        .limit(100)
    ).all()
    return render(request, "history.html", {"rows": rows}, user=user)
