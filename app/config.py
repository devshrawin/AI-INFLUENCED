"""Central configuration.

Every setting can be overridden with an environment variable of the same
name (upper case) or a line in the `.env` file. Secrets must NEVER be
hard-coded here: only safe development defaults live in this file.
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # ACI_ENV_FILE="" disables reading a .env file (used by the test suite).
    model_config = SettingsConfigDict(
        env_file=os.environ.get("ACI_ENV_FILE", ".env") or None, env_file_encoding="utf-8", extra="ignore"
    )

    # --- General -----------------------------------------------------------
    app_name: str = "Upload Integrity Check"
    environment: str = "dev"  # dev | prod
    # Used to sign session cookies. MUST be set in .env for production.
    secret_key: str = Field(default="dev-only-change-me", min_length=8)

    # --- Storage -----------------------------------------------------------
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'app.db'}"
    upload_dir: Path = BASE_DIR / "data" / "uploads"
    # Keep a copy of uploaded files after the check? (Off by default.)
    store_uploads: bool = False
    # Uploads (if stored) are deleted after this many hours.
    retention_hours: int = 24

    # --- Upload limits -----------------------------------------------------
    max_upload_mb: int = 25
    max_embedded_images: int = 10  # images pulled out of one document

    # --- Antivirus (ClamAV) -----------------------------------------------
    clamav_enabled: bool = True  # used only if clamd is reachable
    clamav_socket: str = "/var/run/clamav/clamd.ctl"
    clamav_required: bool = False  # if True, reject uploads when ClamAV is down

    # --- Provenance ------------------------------------------------------
    # Optional PEM file of trusted C2PA root certificates (copy the official
    # C2PA trust list here). Without it, signatures are still verified but
    # the signer is reported as "not on the local trust list".
    c2pa_trust_anchors_file: Path | None = None

    # --- Duplicate photos --------------------------------------------------
    # Fingerprint distance (0-64 bits). Measured on 53 real photos (Nov 2026):
    # WhatsApp-style copies 0-2; copies cropped 2-5% mostly 4-10;
    # unrelated photos never below 20 (median 30).
    same_photo_max_distance: int = 10  # <= this: "same photo" (high)
    similar_photo_max_distance: int = 16  # <= this: "very similar photo" (review)

    # --- Security -----------------------------------------------------------
    rate_limit: str = "30/minute"  # per officer for manual checks in the web page
    # API keys for the scheme platform (comma-separated). Empty = API disabled.
    api_keys: str = ""
    api_rate_limit: str = "600/minute"  # per API key
    session_max_age_hours: int = 8
    cookie_secure: bool = False  # set True when served over HTTPS
    auth_provider: str = "local"  # local | ldap (see app/auth/providers.py)
    # Created on first start if no users exist. Change password immediately.
    bootstrap_admin_user: str = "admin"
    bootstrap_admin_password: str = ""  # empty -> no bootstrap admin

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


def api_key_list(settings: Settings) -> list[str]:
    return [k.strip() for k in settings.api_keys.split(",") if len(k.strip()) >= 16]
