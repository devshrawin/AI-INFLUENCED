"""Session login state, CSRF protection and role checks (FastAPI dependencies)."""

from __future__ import annotations

import hmac
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.models import AuditLog, User
from app.db.session import get_db

MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15


class LoginRequired(Exception):
    """Raised for anonymous users; the app turns it into a redirect to /login."""


class PasswordChangeRequired(Exception):
    """Raised until a user with a temporary password sets their own."""


# Pages a user with a temporary password may still open.
_PASSWORD_CHANGE_ALLOWED = ("/account/password", "/logout")


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


async def verify_csrf(request: Request) -> None:
    """Every state-changing request must carry the session's CSRF token,
    either as header X-CSRF-Token (HTMX) or form field csrf_token."""
    expected = request.session.get("csrf", "")
    sent = request.headers.get("X-CSRF-Token", "")
    if not sent:
        form = await request.form()
        sent = str(form.get("csrf_token", ""))
    if not expected or not hmac.compare_digest(expected, sent):
        raise HTTPException(status_code=403, detail="Security token missing or expired. Reload the page.")


def client_ip(request: Request) -> str:
    # Nginx sets X-Real-IP; uvicorn --proxy-headers handles X-Forwarded-For.
    return request.headers.get("X-Real-IP") or (request.client.host if request.client else "")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    if uid is None:
        raise LoginRequired()
    user = db.get(User, uid)
    if user is None or not user.is_active:
        request.session.clear()
        raise LoginRequired()
    if user.must_change_password and request.url.path not in _PASSWORD_CHANGE_ALLOWED:
        raise PasswordChangeRequired()
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return user


def record_event(db: Session, event: str, request: Request, user: User | None, detail: str = "", username=""):
    db.add(
        AuditLog(
            event=event,
            user_id=user.id if user else None,
            username=user.username if user else username,
            client_ip=client_ip(request),
            detail=detail[:500],
        )
    )
    db.commit()


def is_locked(user: User) -> bool:
    if user.locked_until is None:
        return False
    until = user.locked_until if user.locked_until.tzinfo else user.locked_until.replace(tzinfo=UTC)
    return until > datetime.now(UTC)


def register_failure(db: Session, user: User) -> None:
    user.failed_logins += 1
    if user.failed_logins >= MAX_FAILED_LOGINS:
        user.locked_until = datetime.now(UTC) + timedelta(minutes=LOCKOUT_MINUTES)
        user.failed_logins = 0
    db.commit()
