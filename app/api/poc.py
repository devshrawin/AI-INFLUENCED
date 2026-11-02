"""Proof-of-concept page: no login, two tabs.

    GET  /               the page
    POST /poc/ai         tab 1: AI check of one file (metadata only, nothing stored)
    POST /poc/duplicates tab 2: upload pictures, find ones already uploaded before
    POST /poc/reset      forget every picture uploaded in tab 2
"""

from __future__ import annotations

import base64
import io
import secrets

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.templating import templates
from app.config import get_settings
from app.db.models import Fingerprint
from app.db.session import get_db
from app.pipeline.check import PartialResult, Submission, ai_check, duplicate_check
from app.pipeline.validate import ValidationError, validate_upload

router = APIRouter()


def _page(request: Request, name: str, context: dict | None = None, status_code: int = 200):
    ctx = {"settings": get_settings()}
    ctx.update(context or {})
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def _thumb(data: bytes) -> str | None:
    """Small data: URI preview of an image upload (None for PDF/DOCX)."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.thumbnail((320, 320))
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "JPEG", quality=80)
    except Exception:  # noqa: BLE001 - a preview is optional
        return None
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _stored_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Fingerprint)) or 0


@router.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    return _page(request, "poc.html", {"stored": _stored_count(db)})


@router.post("/poc/ai")
async def poc_ai(request: Request, file: UploadFile = File(...)):
    settings = get_settings()
    data = await file.read(settings.max_upload_bytes + 1)
    try:
        vf = validate_upload(data, file.filename or "", settings)
    except ValidationError as exc:
        return _page(request, "_poc_error.html", {"message": str(exc)}, 400)
    result: PartialResult = await run_in_threadpool(ai_check, vf, settings)
    return _page(request, "_poc_ai.html", {"r": result, "thumb": _thumb(data)})


@router.post("/poc/duplicates")
async def poc_duplicates(request: Request, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    settings = get_settings()
    items = []
    for f in files:
        data = await f.read(settings.max_upload_bytes + 1)
        name = (f.filename or "upload")[:150]
        try:
            vf = validate_upload(data, name, settings)
        except ValidationError as exc:
            items.append({"name": name, "error": str(exc)})
            continue
        # Every upload counts as a different applicant, so the same picture
        # uploaded twice (even by the same person) is reported as a duplicate.
        token = secrets.token_hex(3)
        sub = Submission(f"{name} #{token}", f"poc-{token}")
        result: PartialResult = await run_in_threadpool(duplicate_check, vf, sub, db, settings)
        items.append({"name": name, "r": result, "thumb": _thumb(data)})
    return _page(request, "_poc_dup.html", {"items": items, "stored": _stored_count(db)})


@router.post("/poc/reset")
def poc_reset(request: Request, db: Session = Depends(get_db)):
    db.execute(delete(Fingerprint))
    db.commit()
    return _page(request, "_poc_reset.html", {"stored": 0})
