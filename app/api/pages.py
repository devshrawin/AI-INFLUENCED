"""Officer pages: upload form, result, own history."""

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.limiter import limiter
from app.api.templating import render
from app.auth.security import client_ip, current_user, verify_csrf
from app.config import get_settings
from app.db.models import AuditLog, User
from app.db.session import get_db
from app.pipeline.orchestrator import analyze
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
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    # Read at most limit+1 bytes so huge uploads are refused cheaply.
    data = await file.read(settings.max_upload_bytes + 1)
    try:
        vf = validate_upload(data, file.filename or "", settings)
    except ValidationError as exc:
        db.add(
            AuditLog(
                event="rejected",
                user_id=user.id,
                username=user.username,
                client_ip=client_ip(request),
                file_name=(file.filename or "")[:255],
                file_size=len(data),
                detail=str(exc)[:500],
            )
        )
        db.commit()
        return render(request, "_error.html", {"message": str(exc)}, 400, user=user)
    # Model inference is slow and blocking: run it off the event loop.
    result = await run_in_threadpool(analyze, vf, settings)
    row = await run_in_threadpool(record_check, db, user, client_ip(request), vf, result, settings)
    return render(request, "_result.html", {"r": result, "audit_id": row.id}, user=user)


@router.get("/history")
def history(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.user_id == user.id, AuditLog.event == "check")
        .order_by(AuditLog.created_at.desc())
        .limit(100)
    ).all()
    return render(request, "history.html", {"rows": rows}, user=user)
