"""Login, logout and password change."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.limiter import limiter
from app.api.templating import render
from app.auth.passwords import hash_password, password_problem, verify_password
from app.auth.providers import get_provider
from app.auth.security import current_user, is_locked, record_event, register_failure, verify_csrf
from app.config import get_settings
from app.db.models import User
from app.db.session import get_db

router = APIRouter()


@router.get("/login")
def login_form(request: Request):
    return render(request, "login.html")


@router.post("/login", dependencies=[Depends(verify_csrf)])
@limiter.limit("10/minute")
def login(
    request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)
):
    username = username.strip()[:150]
    outcome = get_provider(get_settings()).authenticate(db, username, password)
    user = outcome.user
    if user is not None and is_locked(user):
        record_event(db, "login_locked", request, user)
        return render(request, "login.html", {"error": "Account temporarily locked. Try again later."}, 403)
    if outcome.message or user is None or not user.is_active:
        if user is not None:
            register_failure(db, user)
        record_event(db, "login_failed", request, None, username=username)
        return render(request, "login.html", {"error": outcome.message or "Account disabled."}, 401)

    user.failed_logins = 0
    user.locked_until = None
    user.last_login = datetime.now(UTC)
    db.commit()
    request.session.clear()  # new session on login (prevents session fixation)
    request.session["uid"] = user.id
    record_event(db, "login", request, user)
    target = "/account/password" if user.must_change_password else "/"
    return RedirectResponse(target, status_code=303)


@router.post("/logout", dependencies=[Depends(verify_csrf)])
def logout(request: Request, db: Session = Depends(get_db)):
    uid = request.session.get("uid")
    user = db.get(User, uid) if uid else None
    if user:
        record_event(db, "logout", request, user)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/account/password")
def password_form(request: Request, user: User = Depends(current_user)):
    return render(request, "password.html", user=user)


@router.post("/account/password", dependencies=[Depends(verify_csrf)])
def change_password(
    request: Request,
    current: str = Form(...),
    new: str = Form(...),
    confirm: str = Form(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    error = None
    if user.auth_source != "local":
        error = "Your password is managed by the department directory."
    elif not verify_password(user.password_hash, current):
        error = "Current password is wrong."
    elif new != confirm:
        error = "New passwords do not match."
    else:
        error = password_problem(new)
    if error:
        return render(request, "password.html", {"error": error}, 400, user=user)
    user.password_hash = hash_password(new)
    user.must_change_password = False
    db.commit()
    record_event(db, "password_changed", request, user)
    return render(request, "password.html", {"ok": "Password changed."}, user=user)
