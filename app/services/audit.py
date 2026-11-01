"""Write a check result to the audit log (and optionally keep the file)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import AuditLog, User
from app.pipeline.orchestrator import AnalysisResult
from app.pipeline.validate import ValidatedFile

EXTENSIONS = {"pdf": "pdf", "docx": "docx", "txt": "txt", "jpeg": "jpg", "png": "png", "webp": "webp"}


def store_upload(vf: ValidatedFile, settings: Settings) -> str:
    """Save the uploaded file (only if STORE_UPLOADS=true). Name = hash, not user file name."""
    day = datetime.now(UTC).strftime("%Y%m%d")
    folder = Path(settings.upload_dir) / day
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{vf.sha256}.{EXTENSIONS.get(vf.kind, 'bin')}"
    path.write_bytes(vf.data)
    path.chmod(0o600)
    return str(path)


def audit_scores(result: AnalysisResult) -> dict:
    """Scores and signal summary only - never document text or excerpts."""
    return {
        "signals": [
            {
                "name": s.name,
                "source": s.source,
                "target": s.target,
                "score": s.score,
                "weight": s.weight,
                "model_id": s.model_id,
            }
            for s in result.signals
        ],
        "chunks": [{"index": c.index, "score": c.score, "words": c.words} for c in result.chunks],
        "explanation": result.explanation,
        "language": (result.language or {}).get("name"),
        "provenance": {
            k: (result.provenance or {}).get(k)
            for k in (
                "c2pa_present",
                "c2pa_state",
                "c2pa_trusted",
                "ai_declared_type",
                "generator",
                "confirmed_ai",
            )
        },
    }


def record_check(
    db: Session,
    user: User,
    client_ip: str,
    vf: ValidatedFile,
    result: AnalysisResult,
    settings: Settings,
) -> AuditLog:
    stored = store_upload(vf, settings) if settings.store_uploads else None
    row = AuditLog(
        event="check",
        user_id=user.id,
        username=user.username,
        client_ip=client_ip,
        file_name=vf.filename,
        sha256=vf.sha256,
        file_type=vf.kind,
        file_size=vf.size,
        final_score=result.final_score,
        label=result.label,
        scores=audit_scores(result),
        model_versions=result.model_versions(),
        warnings=result.warnings,
        av_status=vf.av_status,
        duration_s=result.duration_s,
        stored_path=stored,
    )
    db.add(row)
    db.commit()
    return row
