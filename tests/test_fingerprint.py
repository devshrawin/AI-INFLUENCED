"""Photo fingerprints must survive common re-saving, and must not match unrelated photos."""

import io

import pytest
from PIL import Image, ImageEnhance

from app.pipeline import fingerprint as fp


def _img(data):
    return Image.open(io.BytesIO(data)).convert("RGB")


def _bytes(img, fmt="JPEG", **kw):
    buf = io.BytesIO()
    img.save(buf, fmt, **kw)
    return buf.getvalue()


def _variants(data):
    im = _img(data)
    w, h = im.size
    return {
        "resized 50%": _bytes(im.resize((w // 2, h // 2))),
        "jpeg quality 40": _bytes(im, quality=40),
        "brighter 20%": _bytes(ImageEnhance.Brightness(im).enhance(1.2)),
        "whatsapp-like 800px q60": _bytes(im.resize((800, int(800 * h / w))), quality=60),
        "png": _bytes(im, "PNG"),
        "crop 5%": _bytes(im.crop((int(w * 0.05), int(h * 0.05), w, h))),
    }


@pytest.mark.parametrize("name", ["resized 50%", "jpeg quality 40", "brighter 20%", "whatsapp-like 800px q60",
                                  "png", "crop 5%"])  # fmt: skip
def test_copies_stay_close(sample, name):
    original = fp.phash(sample("photo1.jpg"))
    copy = fp.phash(_variants(sample("photo1.jpg"))[name])
    assert fp.distance(original, copy) <= 8, name


def test_different_photos_far_apart(sample):
    assert fp.distance(fp.phash(sample("photo1.jpg")), fp.phash(sample("photo2.jpg"))) > 16


def test_blank_image_has_no_fingerprint():
    assert fp.phash(_bytes(Image.new("RGB", (400, 300), (250, 250, 250)))) is None


def test_hex_roundtrip(sample):
    h = fp.phash(sample("photo1.jpg"))
    assert fp.from_hex(fp.to_hex(h)) == h and len(fp.to_hex(h)) == 16


def test_document_vs_photo(sample):
    assert fp.looks_like_document(sample("marksheet1.png"))
    assert not fp.looks_like_document(sample("photo1.jpg"))
    # A grey phone photo of paper still counts as a document.
    grey = ImageEnhance.Brightness(_img(sample("marksheet1.png"))).enhance(0.7)
    assert fp.looks_like_document(_bytes(grey))


def test_why_documents_are_not_visually_matched(sample):
    """Two DIFFERENT students' marksheets get nearly the same fingerprint - the
    reason documents are only matched as exact files."""
    a, b = fp.phash(sample("marksheet1.png")), fp.phash(sample("marksheet2.png"))
    assert fp.distance(a, b) <= 8
