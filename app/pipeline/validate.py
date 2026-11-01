"""Step 1: validate an uploaded file before anything else touches it.

Checks, in order:
  1. size limit
  2. real file type from magic bytes (the file name/extension is ignored)
  3. antivirus scan with ClamAV, if a clamd daemon is reachable
"""

from __future__ import annotations

import hashlib
import io
import logging
import zipfile
from dataclasses import dataclass

import magic

from app.config import Settings
from app.pipeline import clamav

log = logging.getLogger(__name__)

# Our internal short names for each accepted type.
IMAGE_KINDS = {"jpeg", "png", "webp"}
DOCUMENT_KINDS = {"pdf", "docx", "txt"}

_MIME_TO_KIND = {
    "application/pdf": "pdf",
    "image/jpeg": "jpeg",
    "image/png": "png",
    "image/webp": "webp",
    "text/plain": "txt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class ValidationError(Exception):
    """Raised when a file must be rejected. The message is shown to the user."""


@dataclass
class ValidatedFile:
    data: bytes
    filename: str
    kind: str  # one of IMAGE_KINDS | DOCUMENT_KINDS
    mime: str
    sha256: str
    size: int
    av_status: str  # "clean" | "not_scanned" | "unavailable"

    @property
    def is_image(self) -> bool:
        return self.kind in IMAGE_KINDS


# Protection against "zip bombs" (tiny DOCX files that expand to gigabytes)
# and "decompression bomb" images (huge pixel counts that exhaust memory).
MAX_DOCX_UNCOMPRESSED = 300 * 1024 * 1024
MAX_IMAGE_PIXELS = 60_000_000  # 60 megapixels


def _looks_like_docx(data: bytes) -> bool:
    """libmagic sometimes reports DOCX as a plain zip; confirm by contents."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
    except zipfile.BadZipFile:
        return False
    names = {i.filename for i in infos}
    if not ("[Content_Types].xml" in names and "word/document.xml" in names):
        return False
    if sum(i.file_size for i in infos) > MAX_DOCX_UNCOMPRESSED:
        raise ValidationError("The Word document expands to an unsafe size and was rejected.")
    return True


def _check_image(data: bytes) -> None:
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as im:
            width, height = im.size
            if width * height > MAX_IMAGE_PIXELS:
                raise ValidationError(f"The image is too large ({width}x{height} pixels).")
            im.verify()  # structural check without decoding all pixels
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError("The image file is damaged and cannot be read.") from exc


def _is_text(data: bytes) -> bool:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return b"\x00" not in data


def detect_kind(data: bytes) -> tuple[str, str]:
    """Return (kind, mime) from magic bytes or raise ValidationError."""
    mime = magic.from_buffer(data[:8192] if len(data) > 8192 else data, mime=True)
    # Office files are zips; need the whole buffer to check.
    if mime in ("application/zip", "application/octet-stream", DOCX_MIME) and _looks_like_docx(data):
        return "docx", DOCX_MIME
    if mime == DOCX_MIME:  # claims DOCX but structure is wrong
        raise ValidationError("The file claims to be a Word document but is damaged.")
    # Anything text-ish that is valid UTF-8 is accepted as plain text.
    if mime.startswith("text/") and _is_text(data):
        return "txt", "text/plain"
    kind = _MIME_TO_KIND.get(mime)
    if kind is None or kind == "txt":
        raise ValidationError(f"Unsupported file type ({mime}). Allowed: PDF, DOCX, TXT, JPG, PNG, WEBP.")
    return kind, mime


def scan_with_clamav(data: bytes, settings: Settings) -> str:
    """Scan with clamd. Returns status; raises ValidationError if infected."""
    if not settings.clamav_enabled:
        return "not_scanned"
    try:
        status, signature = clamav.scan_bytes(data, settings.clamav_socket)
    except OSError as exc:  # daemon missing / socket error
        if settings.clamav_required:
            raise ValidationError("Virus scanner is unavailable; upload refused.") from exc
        log.warning("ClamAV unavailable, file not scanned: %s", exc)
        return "unavailable"
    if status == "FOUND":
        raise ValidationError(f"The file was rejected by the virus scanner ({signature}).")
    if status != "OK":
        if settings.clamav_required:
            raise ValidationError("Virus scan failed; upload refused.")
        return "unavailable"
    return "clean"


def validate_upload(data: bytes, filename: str, settings: Settings) -> ValidatedFile:
    if not data:
        raise ValidationError("The file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise ValidationError(f"The file is larger than the {settings.max_upload_mb} MB limit.")
    kind, mime = detect_kind(data)
    if kind in IMAGE_KINDS:
        _check_image(data)
    av_status = scan_with_clamav(data, settings)
    return ValidatedFile(
        data=data,
        filename=(filename or "upload")[:255],
        kind=kind,
        mime=mime,
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
        av_status=av_status,
    )
