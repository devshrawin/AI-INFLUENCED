"""Write a check result to the audit log (and optionally keep the file)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import AuditLog, User
from app.pipeline.check import CheckResult
from app.pipeline.validate import ValidatedFile

EXTENSIONS = {"pdf": "pdf", "docx": "docx", "jpeg": "jpg", "png": "png", "webp": "webp"}


def store_upload(vf: ValidatedFile, settings: Settings) -> str:
    """Save the uploaded file (only if STORE_UPLOADS=true). Name = hash, not user file name."""
    day = datetime.now(UTC).strftime("%Y%m%d")
    folder = Path(settings.upload_dir) / day
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{vf.sha256}.{EXTENSIONS.get(vf.kind, 'bin')}"
    path.write_bytes(vf.data)
    path.chmod(0o600)
    return str(path)


def record_check(
    db: Session,
    username: str,
    user: User | None,
    client_ip: str,
    vf: ValidatedFile,
    result: CheckResult,
    settings: Settings,
) -> AuditLog:
    """`username` is the officer, or "api:<key name>" for platform calls."""
    stored = store_upload(vf, settings) if settings.store_uploads else None
    row = AuditLog(
        event="check",
        user_id=user.id if user else None,
        username=username,
        application_id=result.application_id,
        applicant_id=result.applicant_id,
        client_ip=client_ip,
        file_name=vf.filename,
        sha256=vf.sha256,
        file_type=vf.kind,
        file_size=vf.size,
        flag_level=result.level,
        flags=[f.to_dict() for f in result.flags],
        warnings=result.warnings,
        av_status=vf.av_status,
        duration_s=result.duration_s,
        stored_path=stored,
    )
    db.add(row)
    db.commit()
    return row
