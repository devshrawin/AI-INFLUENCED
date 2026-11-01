"""Document extraction: text, embedded images and metadata.

* PDF  -> pypdf
* DOCX -> python-docx (images read straight from the word/media/ folder)
* TXT  -> decoded as UTF-8
"""

from __future__ import annotations

import io
import logging
import zipfile

from app.pipeline.types import ExtractedDocument

log = logging.getLogger(__name__)

MIN_IMAGE_SIDE = 64  # skip icons, bullets and spacer images (pixels)
IMAGE_MAGIC = (b"\xff\xd8\xff", b"\x89PNG", b"RIFF")


def _is_image(blob: bytes) -> bool:
    """True for a real JPEG/PNG/WEBP picture that is not tiny."""
    if not blob.startswith(IMAGE_MAGIC):
        return False
    from PIL import Image

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
            return ExtractedDocument("", [], {}, ["PDF is password-protected; nothing could be read."])

    texts, images = [], []
    for page_no, page in enumerate(reader.pages, start=1):
        try:
            texts.append(page.extract_text() or "")
        except Exception as exc:
            notes.append(f"Page {page_no}: text could not be read ({exc}).")
        if len(images) >= max_images:
            continue
        try:
            for img in page.images:
                # Re-encode to PNG/JPEG via Pillow so the detector gets a normal image.
                pil = img.image
                if pil is None or min(pil.size) < MIN_IMAGE_SIDE:
                    continue
                buf = io.BytesIO()
                pil.convert("RGB").save(buf, "PNG")
                images.append(buf.getvalue())
                if len(images) >= max_images:
                    break
        except Exception as exc:
            notes.append(f"Page {page_no}: images could not be read ({exc}).")

    meta = {}
    if reader.metadata:
        for key, value in reader.metadata.items():
            if value is not None:
                meta[str(key).lstrip("/")] = str(value)[:300]
    text = "\n".join(texts).strip()
    if not text and reader.pages:
        notes.append("No text layer found (scanned PDF?). OCR is not performed by this tool.")
    return ExtractedDocument(text, images, meta, notes)


def extract_docx(data: bytes, max_images: int) -> ExtractedDocument:
    import docx

    document = docx.Document(io.BytesIO(data))
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    text = "\n".join(p for p in parts if p.strip())

    images = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in sorted(zf.namelist()):
            if name.startswith("word/media/") and len(images) < max_images:
                blob = zf.read(name)
                if _is_image(blob):
                    images.append(blob)

    cp = document.core_properties
    meta = {
        k: str(v)
        for k, v in {
            "author": cp.author,
            "last_modified_by": cp.last_modified_by,
            "created": cp.created,
            "modified": cp.modified,
            "title": cp.title,
            "comments": cp.comments,
        }.items()
        if v
    }
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        if "docProps/app.xml" in zf.namelist():
            app_xml = zf.read("docProps/app.xml").decode("utf-8", "replace")
            start = app_xml.find("<Application>")
            if start >= 0:
                meta["application"] = app_xml[start + 13 : app_xml.find("</Application>")][:200]
    return ExtractedDocument(text, images, meta, [])


def extract_txt(data: bytes) -> ExtractedDocument:
    text = data.decode("utf-8-sig", errors="replace")
    return ExtractedDocument(text.strip(), [], {}, [])


def extract_document(
    kind: str, data: bytes, max_images: int = 10, max_chars: int = 200_000
) -> ExtractedDocument:
    if kind == "pdf":
        doc = extract_pdf(data, max_images)
    elif kind == "docx":
        doc = extract_docx(data, max_images)
    elif kind == "txt":
        doc = extract_txt(data)
    else:
        raise ValueError(f"not a document type: {kind}")
    if len(doc.text) > max_chars:
        doc.notes.append(f"Only the first {max_chars:,} characters were analysed.")
        doc.text = doc.text[:max_chars]
    return doc
