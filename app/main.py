"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from starlette.middleware.sessions import SessionMiddleware

from app.api import admin, auth, pages, platform
from app.api.limiter import limiter
from app.api.templating import render
from app.auth.passwords import hash_password
from app.auth.security import LoginRequired, PasswordChangeRequired
from app.config import BASE_DIR, Settings, get_settings
from app.db.models import User
from app.db.session import init_db, new_session
from app.services.retention import RetentionWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

SECURITY_HEADERS = {
    # Only our own server may provide scripts, styles, images, fonts.
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
        "form-action 'self'; base-uri 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
}


def check_settings(settings: Settings) -> None:
    if settings.environment == "prod":
        if settings.secret_key in ("dev-only-change-me", "") or len(settings.secret_key) < 32:
            raise RuntimeError("SECRET_KEY must be set to a random value of 32+ characters in production.")
        if not settings.cookie_secure:
            log.warning("COOKIE_SECURE is false in production; enable it once HTTPS is configured.")


def bootstrap_admin(settings: Settings) -> None:
    """Create the first admin from .env if the user table is empty."""
    if not settings.bootstrap_admin_password:
        return
    with new_session() as db:
        if db.scalar(select(func.count()).select_from(User)):
            return
        db.add(
            User(
                username=settings.bootstrap_admin_user,
                full_name="Initial administrator",
                role="admin",
                password_hash=hash_password(settings.bootstrap_admin_password),
                must_change_password=True,
            )
        )
        try:
            db.commit()
        except IntegrityError:  # another worker process created it at the same moment
            db.rollback()
            return
        log.warning("Created bootstrap admin '%s'. Change its password now.", settings.bootstrap_admin_user)


def create_app(start_background: bool = True) -> FastAPI:
    settings = get_settings()
    check_settings(settings)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        init_db()
        bootstrap_admin(settings)
        worker = None
        if start_background:
            worker = RetentionWorker(settings)
            worker.start()
        yield
        if worker:
            worker.stop_event.set()

    app = FastAPI(title=settings.app_name, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.limiter = limiter
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="aci_session",
        max_age=settings.session_max_age_hours * 3600,
        same_site="strict",
        https_only=settings.cookie_secure,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response

    @app.exception_handler(LoginRequired)
    async def to_login(request: Request, _exc):
        if request.headers.get("HX-Request"):
            # HTMX: tell the browser to do a full redirect.
            return RedirectResponse("/login", status_code=200, headers={"HX-Redirect": "/login"})
        return RedirectResponse("/login", status_code=303)

    @app.exception_handler(PasswordChangeRequired)
    async def to_password(request: Request, _exc):
        if request.headers.get("HX-Request"):
            return RedirectResponse(
                "/account/password", status_code=200, headers={"HX-Redirect": "/account/password"}
            )
        return RedirectResponse("/account/password", status_code=303)

    def is_api(request: Request) -> bool:
        return request.url.path.startswith("/api/")

    @app.exception_handler(RateLimitExceeded)
    async def too_many(request: Request, _exc):
        if is_api(request):
            return JSONResponse({"error": "Rate limit exceeded."}, status_code=429)
        return render(request, "_error.html", {"message": "Too many requests. Please wait a minute."}, 429)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        if is_api(request):
            return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
        return render(request, "_error.html", {"message": exc.detail}, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError):
        if is_api(request):
            fields = sorted({".".join(str(p) for p in e["loc"][1:]) for e in exc.errors()})
            return JSONResponse({"error": "Missing or invalid fields: " + ", ".join(fields)}, status_code=422)
        return render(request, "_error.html", {"message": "Please fill in all required fields."}, 422)

    app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
    app.include_router(auth.router)
    app.include_router(pages.router)
    app.include_router(admin.router)
    app.include_router(platform.router)

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"status": "ok"}

    return app


app = create_app()
