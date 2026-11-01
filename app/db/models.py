"""Database tables: users and the audit log."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ROLES = ("admin", "officer")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    # Empty for users who log in through an external directory (LDAP/SSO).
    password_hash: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[str] = mapped_column(String(20), default="officer")
    auth_source: Mapped[str] = mapped_column(String(20), default="local")  # local | ldap | sso
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class AuditLog(Base):
    """One row per check (and per security event). Never stores file contents."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    event: Mapped[str] = mapped_column(String(30), default="check", index=True)  # check | login | ...
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(150), default="")
    application_id: Mapped[str] = mapped_column(String(100), default="", index=True)
    applicant_id: Mapped[str] = mapped_column(String(100), default="", index=True)
    client_ip: Mapped[str] = mapped_column(String(64), default="")
    file_name: Mapped[str] = mapped_column(String(255), default="")
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    file_type: Mapped[str] = mapped_column(String(20), default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    # Overall flag: high | review | none
    flag_level: Mapped[str] = mapped_column(String(10), default="", index=True)
    # The individual flags (codes, messages, matching applications) as JSON.
    flags: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    av_status: Mapped[str] = mapped_column(String(20), default="")
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)
    stored_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    detail: Mapped[str] = mapped_column(String(500), default="")  # for non-check events


class Fingerprint(Base):
    """One row per uploaded file (and per photo inside it) so later uploads can
    be compared. Stores only hashes and IDs - never the image itself."""

    __tablename__ = "fingerprints"
    __table_args__ = (Index("ix_fp_kind_phash", "kind", "phash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    application_id: Mapped[str] = mapped_column(String(100), index=True)
    applicant_id: Mapped[str] = mapped_column(String(100), index=True)
    scheme: Mapped[str] = mapped_column(String(100), default="")
    file_name: Mapped[str] = mapped_column(String(255), default="")
    part: Mapped[str] = mapped_column(String(50), default="file")  # file | embedded image N
    kind: Mapped[str] = mapped_column(String(10))  # photo | document
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    phash: Mapped[str | None] = mapped_column(String(16), nullable=True)  # photos only
