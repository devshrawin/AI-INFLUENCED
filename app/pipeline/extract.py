"""Documents: pull out embedded images and document metadata.

* PDF  -> pypdf
* DOCX -> images straight from the word/media/ folder, metadata from docProps
Embedded images are checked for AI content credentials and metadata.
"""

from __future__ import annotations

import io
import logging
import zipfile

from PIL import Image

from app.pipeline.types import ExtractedDocument

log = logging.getLogger(__name__)

MIN_IMAGE_SIDE = 64  # skip icons, bullets and spacer images (pixels)
IMAGE_MAGIC = (b"\xff\xd8\xff", b"\x89PNG", b"RIFF")


def _is_image(blob: bytes) -> bool:
    """True for a real JPEG/PNG/WEBP picture that is not tiny."""
    if not blob.startswith(IMAGE_MAGIC):
        return False
    try:
        with Image.open(io.BytesIO(blob)) as im:
            return min(im.size) >= MIN_IMAGE_SIDE
    except Exception:
        return False


def extract_pdf(data: bytes, max_images: int) -> ExtractedDocument:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    notes: list[str] = []
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            return ExtractedDocument(
                [], {}, ["PDF is password-protected; its contents could not be checked."]
            )

    images: list[bytes] = []
    for page_no, page in enumerate(reader.pages, start=1):
        if len(images) >= max_images:
            break
        try:
            for img in page.images:
                # Keep the original embedded bytes when they are JPEG/PNG,
                # so their own metadata / credentials are preserved.
                if img.data[:4] in (b"\x89PNG",) or img.data[:3] == b"\xff\xd8\xff":
                    blob = img.data
                else:
                    pil = img.image
                    if pil is None:
                        continue
                    buf = io.BytesIO()
                    pil.convert("RGB").save(buf, "PNG")
                    blob = buf.getvalue()
                if _is_image(blob):
                    images.append(blob)
                if len(images) >= max_images:
                    break
        except Exception as exc:
            notes.append(f"Page {page_no}: images could not be read ({exc}).")

    meta = {}
    if reader.metadata:
        for key, value in reader.metadata.items():
            if value is not None:
                meta[str(key).lstrip("/")] = str(value)[:300]
    return ExtractedDocument(images, meta, notes)


def extract_docx(data: bytes, max_images: int) -> ExtractedDocument:
    images: list[bytes] = []
    meta: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        for name in sorted(names):
            if name.startswith("word/media/") and len(images) < max_images:
                blob = zf.read(name)
                if _is_image(blob):
                    images.append(blob)
        for part in ("docProps/core.xml", "docProps/app.xml"):
            if part in names:
                xml = zf.read(part).decode("utf-8", "replace")
                for tag in ("dc:creator", "cp:lastModifiedBy", "dc:title", "dc:description", "Application"):
                    start = xml.find(f"<{tag}>")
                    if start >= 0:
                        end = xml.find(f"</{tag}>", start)
                        meta[tag.split(":")[-1]] = xml[start + len(tag) + 2 : end][:200]
    return ExtractedDocument(images, meta, [])


def extract_document(kind: str, data: bytes, max_images: int = 10) -> ExtractedDocument:
    if kind == "pdf":
        return extract_pdf(data, max_images)
    if kind == "docx":
        return extract_docx(data, max_images)
    raise ValueError(f"not a document type: {kind}")
