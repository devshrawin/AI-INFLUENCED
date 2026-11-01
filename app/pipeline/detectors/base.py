"""Common pieces for all local detector models."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)


class ModelUnavailable(Exception):
    """Model folder missing or failed to load. The pipeline skips this signal."""


@dataclass
class DetectorOutput:
    score: float  # 0-100, higher = more AI-like
    detail: str = ""


def pick_device(preference: str = "auto") -> str:
    """'cuda' if a GPU is usable (and allowed), otherwise 'cpu'."""
    import torch

    if preference == "cpu":
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if preference == "cuda":
        log.warning("DEVICE=cuda requested but no GPU found; falling back to CPU.")
    return "cpu"


@lru_cache
def read_manifest(models_dir: str) -> dict:
    path = Path(models_dir) / "MANIFEST.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text()).get("models", {})


def model_version(models_dir: Path, folder: str) -> str:
    """Short revision hash from MANIFEST.json, for the audit log."""
    entry = read_manifest(str(models_dir)).get(folder, {})
    rev = entry.get("revision")
    return rev[:12] if rev else "unknown"


def require_model_dir(models_dir: Path, folder: str) -> Path:
    path = Path(models_dir) / folder
    if not (path / "config.json").exists():
        raise ModelUnavailable(f"Model files not found in {path}. Run scripts/download_models.py.")
    return path


class LazyModel:
    """Loads a model on first use, once, thread-safely."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded = False
        self._error: Exception | None = None

    def _load(self) -> None:  # implemented by subclasses
        raise NotImplementedError

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            if self._error is not None:
                raise ModelUnavailable(str(self._error))
            try:
                self._load()
            except ModelUnavailable as exc:
                self._error = exc
                raise
            except Exception as exc:
                self._error = exc
                log.exception("Failed to load model")
                raise ModelUnavailable(f"Model failed to load: {exc}") from exc
            self._loaded = True
