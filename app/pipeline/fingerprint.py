"""Visual fingerprints for finding the same photo uploaded more than once.

We use a "perceptual hash" (pHash): the photo is shrunk to 32x32 grey pixels,
and the 64 lowest-frequency patterns (a DCT, as in JPEG) are compared with
their median. The result is a 64-bit number that stays almost the same when
a photo is resized, re-compressed, brightened, lightly cropped or forwarded
on WhatsApp. Two fingerprints are compared by counting differing bits
(Hamming distance): 0 = identical look, about 30 = unrelated photos.

Measured on 53 real photos (1,378 unrelated pairs): WhatsApp-style copies
(resized + re-compressed) differed by 0-2 bits; copies cropped by 2-5% mostly
by 4-10 bits (some up to 18-24); unrelated photos never by less than 20 bits
(median 30). Heavier crops or edits are not reliably caught.

IMPORTANT: this does NOT work for documents (marksheets, certificates).
Two different students' marksheets with the same printed layout get the
same fingerprint. Documents are therefore only matched as exact files
(SHA-256). `looks_like_document` decides which kind an image is when the
platform does not say.

Pure Python + Pillow; no extra libraries.
"""

from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

_N = 32  # working size
_K = 8  # low-frequency block -> 64 bits
_COS = [[math.cos(math.pi * (2 * x + 1) * u / (2 * _N)) for x in range(_N)] for u in range(_K)]


def _open(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    return ImageOps.exif_transpose(img).convert("L")


def _pixels(img: Image.Image) -> list[int]:
    getter = getattr(img, "get_flattened_data", None) or img.getdata
    return list(getter())


def phash(data: bytes) -> int | None:
    """64-bit perceptual hash, or None for blank / almost uniform images
    (those would all match each other and cause false duplicates)."""
    img = _open(data).resize((_N, _N), Image.Resampling.LANCZOS)
    px = _pixels(img)
    mean = sum(px) / len(px)
    if (sum((p - mean) ** 2 for p in px) / len(px)) ** 0.5 < 5:
        return None
    rows = [px[y * _N : (y + 1) * _N] for y in range(_N)]
    # 2-D DCT, only the 8x8 low-frequency corner is needed.
    tmp = [[sum(r[x] * _COS[u][x] for x in range(_N)) for u in range(_K)] for r in rows]
    coef = [sum(tmp[y][u] * _COS[v][y] for y in range(_N)) for v in range(_K) for u in range(_K)]
    median = sorted(coef[1:])[len(coef[1:]) // 2]  # skip the overall-brightness term
    return sum(1 << i for i, c in enumerate(coef) if c > median)


def distance(a: int, b: int) -> int:
    """Number of differing bits between two fingerprints (0-64)."""
    return (a ^ b).bit_count()


def to_hex(h: int) -> str:
    return f"{h:016x}"


def from_hex(s: str) -> int:
    return int(s, 16)


_DOC_LIGHT_SHARE = 0.55


def _light_share(img: Image.Image) -> float:
    """Share of light pixels after stretching contrast (paper is mostly light)."""
    px = _pixels(ImageOps.autocontrast(img, cutoff=2))
    return sum(p > 200 for p in px) / len(px)


def looks_like_document(data: bytes) -> bool:
    """Heuristic: a scan or photo of paper is mostly light background with
    dark ink. Contrast is stretched first so grey phone photos of paper
    still count."""
    return _light_share(_open(data).resize((128, 128))) > _DOC_LIGHT_SHARE


def classify(data: bytes) -> str:
    """"photo" or "document", chosen so that editing the file does not change the answer.

    A plain `looks_like_document` flips on common edits: brightening a photo by
    30% or adding a caption bar pushed about half of our test photos over the
    line, and the edited copy then skipped visual matching. So an image counts
    as a document only if it still does after a brightness change either way,
    a black caption bar and a white border. Anything unstable is a photo.
    """
    base = _open(data).resize((128, 128))
    barred = base.copy()
    ImageDraw.Draw(barred).rectangle((0, 118, 128, 128), fill=0)
    framed = ImageOps.expand(base, border=8, fill=255)
    views = [
        base,
        ImageEnhance.Brightness(base).enhance(1.3),
        ImageEnhance.Brightness(base).enhance(0.75),
        barred,
        framed,
    ]
    return "document" if all(_light_share(v) > _DOC_LIGHT_SHARE for v in views) else "photo"
