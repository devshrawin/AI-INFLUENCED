"""Administrator pages: user management and the audit log."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.templating import render
from app.auth.passwords import hash_password, password_problem
from app.auth.security import record_event, require_admin, verify_csrf
from app.db.models import ROLES, AuditLog, User
from app.db.session import get_db

router = APIRouter(prefix="/admin")
PAGE_SIZE = 50


# ------------------------------------------------------------------ users
@router.get("/users")
def users(request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(User).order_by(User.username)).all()
    return render(request, "admin_users.html", {"rows": rows, "roles": ROLES}, user=admin)


@router.post("/users", dependencies=[Depends(verify_csrf)])
def create_user(
    request: Request,
    username: str = Form(...),
    full_name: str = Form(""),
    role: str = Form("officer"),
    auth_source: str = Form("local"),
    password: str = Form(""),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    username = username.strip()
    error = None
    if role not in ROLES or auth_source not in ("local", "ldap"):
        error = "Invalid role or login type."
    elif not username or len(username) > 150 or not username.replace(".", "").replace("_", "").isalnum():
        error = "Username may contain letters, numbers, dot and underscore only."
    elif db.scalar(select(User).where(User.username == username)):
        error = "That username already exists."
    elif auth_source == "local":
        error = password_problem(password)
    if error:
        rows = db.scalars(select(User).order_by(User.username)).all()
        return render(
            request, "admin_users.html", {"rows": rows, "roles": ROLES, "error": error}, 400, user=admin
        )
    db.add(
        User(
            username=username,
            full_name=full_name.strip()[:200],
            role=role,
            auth_source=auth_source,
            password_hash=hash_password(password) if auth_source == "local" else "",
            must_change_password=auth_source == "local",
        )
    )
    db.commit()
    record_event(db, "user_created", request, admin, f"{username} ({role}, {auth_source})")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}", dependencies=[Depends(verify_csrf)])
def update_user(
    request: Request,
    user_id: int,
    action: str = Form(...),
    role: str = Form(""),
    password: str = Form(""),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "User not found")
    if target.id == admin.id and action in ("deactivate", "set_role"):
        raise HTTPException(400, "You cannot change your own role or disable yourself.")
    if action == "set_role" and role in ROLES:
        target.role = role
    elif action == "deactivate":
        target.is_active = False
    elif action == "activate":
        target.is_active = True
        target.locked_until = None
    elif action == "reset_password" and target.auth_source == "local":
        problem = password_problem(password)
        if problem:
            raise HTTPException(400, problem)
        target.password_hash = hash_password(password)
        target.must_change_password = True
        target.locked_until = None
    else:
        raise HTTPException(400, "Unknown action")
    db.commit()
    record_event(db, f"user_{action}", request, admin, f"{target.username} {role}".strip())
    return RedirectResponse("/admin/users", status_code=303)


# ------------------------------------------------------------------ audit log
def _audit_query(q: str, event: str, level: str, date_from: str, date_to: str):
    stmt = select(AuditLog)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            AuditLog.username.ilike(like)
            | AuditLog.file_name.ilike(like)
            | AuditLog.sha256.ilike(like)
            | AuditLog.application_id.ilike(like)
            | AuditLog.applicant_id.ilike(like)
        )
    if event:
        stmt = stmt.where(AuditLog.event == event)
    if level:
        stmt = stmt.where(AuditLog.flag_level == level)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= datetime.fromisoformat(date_from))
    if date_to:
        stmt = stmt.where(AuditLog.created_at < datetime.fromisoformat(date_to + "T23:59:59"))
    return stmt


@router.get("/audit")
def audit(
    request: Request,
    q: str = "",
    event: str = "",
    level: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        stmt = _audit_query(q, event, level, date_from, date_to)
    except ValueError:
        raise HTTPException(400, "Dates must be YYYY-MM-DD") from None
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    page = max(page, 1)
    rows = db.scalars(
        stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    ).all()
    filters = {"q": q, "event": event, "level": level, "date_from": date_from, "date_to": date_to}
    return render(
        request,
        "admin_audit.html",
        {"rows": rows, "total": total, "page": page, "pages": max(1, -(-total // PAGE_SIZE)), "f": filters},
        user=admin,
    )


@router.get("/audit/{row_id}")
def audit_detail(
    request: Request, row_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    row = db.get(AuditLog, row_id)
    if row is None:
        raise HTTPException(404, "Not found")
    pretty = json.dumps({"flags": row.flags, "warnings": row.warnings}, indent=2)
    return render(request, "admin_audit_detail.html", {"row": row, "pretty": pretty}, user=admin)


@router.get("/audit.csv")
def audit_csv(
    q: str = "",
    event: str = "",
    level: str = "",
    date_from: str = "",
    date_to: str = "",
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    stmt = _audit_query(q, event, level, date_from, date_to).order_by(AuditLog.created_at.desc())
    cols = [
        "id", "created_at", "event", "username", "application_id", "applicant_id", "client_ip",
        "file_name", "sha256", "file_type", "file_size", "flag_level", "av_status", "duration_s", "detail",
    ]  # fmt: skip

    def rows():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([*cols, "flag_codes"])
        for row in db.scalars(stmt).yield_per(500):
            values = [getattr(row, c) for c in cols]
            # Neutralise spreadsheet formulas in user-controlled text (CSV injection).
            values = ["'" + v if isinstance(v, str) and v[:1] in "=+-@" else v for v in values]
            writer.writerow([*values, " ".join(f.get("code", "") for f in row.flags or [])])
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()

    headers = {"Content-Disposition": "attachment; filename=audit_log.csv"}
    return StreamingResponse(rows(), media_type="text/csv", headers=headers)
