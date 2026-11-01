"""Rate limiting (in-memory, per logged-in user or per IP)."""

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def _key(request: Request) -> str:
    uid = request.session.get("uid") if "session" in request.scope else None
    return f"user:{uid}" if uid else f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=_key)
