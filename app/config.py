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
    app_name: str = "AI Content Indicator"
    environment: str = "dev"  # dev | prod
    # Used to sign session cookies. MUST be set in .env for production.
    secret_key: str = Field(default="dev-only-change-me", min_length=8)

    # --- Storage -----------------------------------------------------------
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'app.db'}"
    upload_dir: Path = BASE_DIR / "data" / "uploads"
    models_dir: Path = BASE_DIR / "models"
    # Keep a copy of uploaded files after the check? (Off by default.)
    store_uploads: bool = False
    # Uploads (if stored) are deleted after this many hours.
    retention_hours: int = 24

    # --- Upload limits -----------------------------------------------------
    max_upload_mb: int = 25
    max_text_chars: int = 200_000  # text beyond this is ignored (with a note)
    max_embedded_images: int = 10  # images pulled out of one document
    # Images smaller than this (shortest side, pixels) are too small to judge.
    min_image_side: int = 128

    # --- Antivirus (ClamAV) -----------------------------------------------
    clamav_enabled: bool = True  # used only if clamd is reachable
    clamav_socket: str = "/var/run/clamav/clamd.ctl"
    clamav_required: bool = False  # if True, reject uploads when ClamAV is down

    # --- Provenance ------------------------------------------------------
    # Optional PEM file of trusted C2PA root certificates (copy the official
    # C2PA trust list here). Without it, signatures are still verified but
    # the signer is reported as "not on local trust list".
    c2pa_trust_anchors_file: Path | None = None

    # --- Labels / thresholds (percent) ---------------------------------------
    threshold_ai: float = 70.0  # score >= this -> "Likely AI"
    threshold_human: float = 30.0  # score < this  -> "Likely Human"

    # --- Detector weights ------------------------------------------------
    weight_image_primary: float = 0.6
    weight_image_secondary: float = 0.4
    weight_text_binoculars: float = 0.5
    weight_text_classifier: float = 0.5
    # Documents: share of the final score for the text vs. embedded images.
    weight_document_text: float = 0.7
    weight_document_images: float = 0.3
    # Max points a weak metadata hint (e.g. "Software: Midjourney") may add.
    metadata_hint_bonus: float = 15.0

    # --- Models -------------------------------------------------------------
    # Folder names under models_dir (written by scripts/download_models.py).
    image_model_primary: str = "haywoodsloan--ai-image-detector-deploy"
    image_model_secondary: str = "Ateeqq--ai-vs-human-image-detector"
    text_model_classifier: str = "desklib--ai-text-detector-v1.01"
    binoculars_observer: str = "Qwen--Qwen2.5-1.5B"
    binoculars_performer: str = "Qwen--Qwen2.5-1.5B-Instruct"
    # Turn individual detectors on/off (e.g. Binoculars off on small servers).
    enable_image_detectors: bool = True
    enable_text_classifier: bool = True
    enable_binoculars: bool = True
    # Binoculars score at which P(AI)=50%, and curve spread. Calibrated for the
    # Qwen2.5-1.5B pair on a public human/ChatGPT sample (about 5% false
    # positives); re-run eval/calibrate_binoculars.py on local data.
    binoculars_threshold: float = 0.90
    binoculars_scale: float = 0.04
    device: str = "auto"  # auto | cpu | cuda
    preload_models: bool = False  # load all models at start-up (prod: true)
    chunk_tokens: int = 384  # words per text chunk (approx.)
    max_chunks: int = 20
    min_words_for_text_score: int = 40

    # --- Security -----------------------------------------------------------
    rate_limit: str = "20/minute"  # per user/IP for the upload endpoint
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
