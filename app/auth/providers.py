"""Pluggable authentication.

Set AUTH_PROVIDER in .env:
  local  - usernames/passwords stored (hashed) in this tool's database
  ldap   - check passwords against the department directory (see LdapProvider)

To add SSO (e.g. SAML/OIDC through a reverse proxy), write a provider with
the same `authenticate` method, or use `HeaderProvider`-style trust of a
header set by the proxy. Roles are always kept in this tool's database so
an admin controls who is "admin" or "officer".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.passwords import verify_password
from app.config import Settings
from app.db.models import User

log = logging.getLogger(__name__)


@dataclass
class AuthOutcome:
    user: User | None
    message: str = ""


class AuthProvider:
    name = "base"

    def authenticate(self, db: Session, username: str, password: str) -> AuthOutcome:
        raise NotImplementedError


class LocalProvider(AuthProvider):
    name = "local"

    def authenticate(self, db: Session, username: str, password: str) -> AuthOutcome:
        user = db.scalar(select(User).where(User.username == username))
        if user is None or user.auth_source != "local":
            # Spend similar time as a real check to avoid username probing.
            verify_password("$argon2id$v=19$m=65536,t=3,p=4$c2FsdHNhbHQ$aGFzaGhhc2hoYXNo", password)
            return AuthOutcome(None, "Invalid username or password.")
        if not verify_password(user.password_hash, password):
            return AuthOutcome(user, "Invalid username or password.")
        return AuthOutcome(user)


class LdapProvider(AuthProvider):
    """Placeholder for the department LDAP / Active Directory.

    To enable:
      1. pip install ldap3 (add to requirements.txt and the offline bundle)
      2. implement `_bind(username, password)` with ldap3.Connection using
         LDAPS (port 636) and the service settings from .env
      3. set AUTH_PROVIDER=ldap
    A user must also exist in this tool's user list (auth_source = "ldap")
    so the admin decides the role.
    """

    name = "ldap"

    def _bind(self, username: str, password: str) -> bool:  # pragma: no cover
        raise NotImplementedError("LDAP login is not configured. See app/auth/providers.py.")

    def authenticate(self, db: Session, username: str, password: str) -> AuthOutcome:
        user = db.scalar(select(User).where(User.username == username, User.auth_source == "ldap"))
        if user is None:
            return AuthOutcome(None, "Invalid username or password.")
        try:
            ok = self._bind(username, password)
        except NotImplementedError as exc:
            log.error("%s", exc)
            return AuthOutcome(None, "Directory login is not available. Contact the administrator.")
        return AuthOutcome(user if ok else None, "" if ok else "Invalid username or password.")


def get_provider(settings: Settings) -> AuthProvider:
    providers = {"local": LocalProvider, "ldap": LdapProvider}
    try:
        return providers[settings.auth_provider]()
    except KeyError:
        raise ValueError(f"Unknown AUTH_PROVIDER={settings.auth_provider!r}") from None
