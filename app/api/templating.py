"""Shared Jinja2 template engine."""

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.auth.security import csrf_token
from app.config import BASE_DIR, get_settings

templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")


def render(request: Request, name: str, context: dict | None = None, status_code: int = 200, user=None):
    """Render a template with the values every page needs."""
    ctx = {"settings": get_settings(), "csrf": csrf_token(request), "user": user}
    ctx.update(context or {})
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)
