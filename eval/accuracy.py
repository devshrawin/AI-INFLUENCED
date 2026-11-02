"""Accuracy evaluation for the Upload Integrity Check.

Takes real photos, makes cropped / edited / re-compressed copies, and measures
what the real pipeline (validate -> classify -> fingerprint -> match) does.

Part A  duplicate detection   recall per edit, wrong matches, false positives, threshold sweep
Part B  AI-metadata detection false positives on real files, injected AI tags, C2PA survival
Part C  false-positive probes  benign metadata that looks like an AI marker

Run from the project root (venv active):
    python eval/accuracy.py --src "C:/Users/me/Downloads" --n 40 --out eval/report.md

No image is uploaded anywhere. Edited copies go to --work (default: temp dir).
Do not commit the photos or the work folder; commit only the report numbers.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import random
import re
import statistics
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ACI_ENV_FILE", "")
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["CLAMAV_ENABLED"] = "false"

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, PngImagePlugin  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.db.session import get_engine, new_session  # noqa: E402
from app.pipeline import fingerprint as fp  # noqa: E402
from app.pipeline.check import Submission, _classify, ai_check, duplicate_flags  # noqa: E402
from app.pipeline.duplicates import register  # noqa: E402
from app.pipeline.validate import ValidationError, validate_upload  # noqa: E402

SETTINGS = get_settings()
SAME, SIMILAR = SETTINGS.same_photo_max_distance, SETTINGS.similar_photo_max_distance
SKIP_NAME = re.compile(r"card|aadhaar|aadhar|pan\b|passport|licen|screenshot|marksheet|certificate|invoice|"
                       r"resume|receipt|salary|bank|id[_ -]|signature", re.I)  # fmt: skip


# ------------------------------------------------------------------ helpers
def enc(img: Image.Image, fmt: str = "JPEG", q: int = 92, **kw) -> bytes:
    buf = io.BytesIO()
    if fmt == "JPEG":
        img = img.convert("RGB")
        img.save(buf, "JPEG", quality=q, **kw)
    elif fmt == "WEBP":
        img.convert("RGB").save(buf, "WEBP", quality=q)
    else:
        img.save(buf, fmt, **kw)
    return buf.getvalue()


def long_edge(img: Image.Image, n: int) -> Image.Image:
    w, h = img.size
    s = n / max(w, h)
    return img.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS) if s < 1 else img.copy()


def scale(img: Image.Image, f: float) -> Image.Image:
    return img.resize((max(8, round(img.width * f)), max(8, round(img.height * f))), Image.LANCZOS)


def crop_c(img: Image.Image, f: float) -> Image.Image:
    w, h = img.size
    cw, ch = round(w * f), round(h * f)
    x, y = (w - cw) // 2, (h - ch) // 2
    return img.crop((x, y, x + cw, y + ch))


def crop_corner(img: Image.Image, f: float, right=False, bottom=False) -> Image.Image:
    w, h = img.size
    cw, ch = round(w * f), round(h * f)
    x = w - cw if right else 0
    y = h - ch if bottom else 0
    return img.crop((x, y, x + cw, y + ch))


def crop_ratio(img: Image.Image, ratio: float) -> Image.Image:
    w, h = img.size
    if w / h > ratio:
        nw = round(h * ratio)
        return img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    nh = round(w / ratio)
    return img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))


def border(img: Image.Image, f: float, colour) -> Image.Image:
    b = round(max(img.size) * f)
    out = Image.new("RGB", (img.width + 2 * b, img.height + 2 * b), colour)
    out.paste(img.convert("RGB"), (b, b))
    return out


def rotate(img: Image.Image, deg: float) -> Image.Image:
    return img.convert("RGB").rotate(deg, expand=True, resample=Image.BICUBIC, fillcolor=(0, 0, 0))


def noise(img: Image.Image, sigma: float) -> Image.Image:
    n = Image.effect_noise(img.size, sigma).convert("RGB")
    return ImageChops.add(img.convert("RGB"), n, scale=1, offset=-128)


def tint(img: Image.Image) -> Image.Image:
    r, g, b = img.convert("RGB").split()
    return Image.merge("RGB", (r.point(lambda v: min(255, v * 1.15 + 12)), g, b.point(lambda v: v * 0.8)))


def gamma(img: Image.Image, g: float) -> Image.Image:
    lut = [round(255 * (i / 255) ** g) for i in range(256)]
    return img.convert("RGB").point(lut * 3)


def caption_bar(img: Image.Image) -> Image.Image:
    out = img.convert("RGB").copy()
    d = ImageDraw.Draw(out)
    h = max(24, out.height // 12)
    d.rectangle((0, out.height - h, out.width, out.height), fill=(0, 0, 0))
    d.text((12, out.height - h + h // 4), "Flood damage - ward 7 - 12/10/2026", fill=(255, 255, 255))
    return out


def sticker(img: Image.Image, frac: float = 0.10) -> Image.Image:
    out = img.convert("RGB").copy()
    d = ImageDraw.Draw(out)
    w, h = out.size
    s = round((w * h * frac) ** 0.5)
    d.ellipse((w - s - 10, 10, w - 10, s + 10), fill=(255, 210, 0), outline=(200, 0, 0), width=4)
    return out


def watermark(img: Image.Image) -> Image.Image:
    base = img.convert("RGBA")
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    step = max(60, base.width // 5)
    for y in range(0, base.height, step):
        for x in range(0, base.width, step):
            d.text((x, y), "SAMPLE", fill=(255, 255, 255, 90))
    return Image.alpha_composite(base, layer).convert("RGB")


def phone_screenshot(img: Image.Image) -> Image.Image:
    """Photo opened in a gallery app and screenshotted: dark bars, scaled to phone width."""
    w = 1080
    inner = img.convert("RGB").resize((w, max(8, round(img.height * w / img.width))), Image.LANCZOS)
    H = max(2340, inner.height + 400)
    out = Image.new("RGB", (w, H), (18, 18, 18))
    out.paste(inner, (0, (H - inner.height) // 2))
    return out


def rescan(img: Image.Image) -> Image.Image:
    g = ImageEnhance.Contrast(img.convert("L").convert("RGB")).enhance(1.25)
    return noise(rotate(g.filter(ImageFilter.GaussianBlur(1)), 2), 15)


# name -> (category, fn(img)->bytes). `robust`: edits the README says should be caught.
def build_transforms():
    J = lambda f, q=92: (lambda im: enc(f(im), "JPEG", q))  # noqa: E731
    T = {}

    def add(name, cat, fn, expect="catch"):
        T[name] = (cat, fn, expect)

    add("re-save jpeg q92", "recompress", J(lambda i: i))
    add("jpeg q70", "recompress", J(lambda i: i, 70))
    add("jpeg q40", "recompress", J(lambda i: i, 40))
    add("jpeg q20", "recompress", J(lambda i: i, 20))
    add("png copy", "recompress", lambda i: enc(i, "PNG"))
    add("webp q75", "recompress", lambda i: enc(i, "WEBP", 75))
    add("resize 75%", "resize", J(lambda i: scale(i, .75)))
    add("resize 50%", "resize", J(lambda i: scale(i, .5)))
    add("resize 25%", "resize", J(lambda i: scale(i, .25)))
    add("WhatsApp (1600px q70)", "messenger", J(lambda i: long_edge(i, 1600), 70))
    add("WhatsApp heavy (1024px q55)", "messenger", J(lambda i: long_edge(i, 1024), 55))
    add("brightness +30%", "colour", J(lambda i: ImageEnhance.Brightness(i.convert("RGB")).enhance(1.3)))
    add("brightness -30%", "colour", J(lambda i: ImageEnhance.Brightness(i.convert("RGB")).enhance(.7)))
    add("contrast +40%", "colour", J(lambda i: ImageEnhance.Contrast(i.convert("RGB")).enhance(1.4)))
    add("greyscale", "colour", J(lambda i: i.convert("L")))
    add("saturation +60%", "colour", J(lambda i: ImageEnhance.Color(i.convert("RGB")).enhance(1.6)))
    add("warm tint", "colour", J(tint))
    add("gamma 0.6", "colour", J(lambda i: gamma(i, .6)))
    add("blur r2", "filter", J(lambda i: i.convert("RGB").filter(ImageFilter.GaussianBlur(2))))
    add("blur r5", "filter", J(lambda i: i.convert("RGB").filter(ImageFilter.GaussianBlur(5))))
    add("sharpen x2", "filter", J(lambda i: ImageEnhance.Sharpness(i.convert("RGB")).enhance(3)))
    add("noise s10", "filter", J(lambda i: noise(i, 10)))
    add("noise s25", "filter", J(lambda i: noise(i, 25)))
    for f in (.98, .95, .90, .80, .70, .50):
        add(f"crop centre {round(f*100)}%", "crop", J(lambda i, f=f: crop_c(i, f)))
    add("crop top-left 85%", "crop", J(lambda i: crop_corner(i, .85)))
    add("crop bottom-right 85%", "crop", J(lambda i: crop_corner(i, .85, True, True)))
    add("crop to 16:9", "crop", J(lambda i: crop_ratio(i, 16 / 9)))
    add("crop to square", "crop", J(lambda i: crop_ratio(i, 1.0)))
    add("white border 5%", "frame", J(lambda i: border(i, .05, (255, 255, 255))))
    add("black border 10%", "frame", J(lambda i: border(i, .10, (0, 0, 0))))
    add("phone screenshot of photo", "frame", lambda i: enc(phone_screenshot(i), "PNG"))
    add("caption bar bottom", "overlay", J(caption_bar))
    add("sticker 10% area", "overlay", J(sticker))
    add("repeating watermark", "overlay", J(watermark))
    add("rotate 5 deg", "geometry", J(lambda i: rotate(i, 5)), "hard")
    add("rotate 15 deg", "geometry", J(lambda i: rotate(i, 15)), "hard")
    add("rotate 90 deg", "geometry", J(lambda i: rotate(i, 90)), "hard")
    add("rotate 180 deg", "geometry", J(lambda i: rotate(i, 180)), "hard")
    add("mirror left-right", "geometry", J(lambda i: i.convert("RGB").transpose(Image.FLIP_LEFT_RIGHT)), "hard")
    add("mirror top-bottom", "geometry", J(lambda i: i.convert("RGB").transpose(Image.FLIP_TOP_BOTTOM)), "hard")
    add("WhatsApp + crop 90%", "combo", J(lambda i: long_edge(crop_c(i, .9), 1600), 70))
    add("crop 90% + bright + q60", "combo",
        J(lambda i: ImageEnhance.Brightness(crop_c(i, .9).convert("RGB")).enhance(1.2), 60))  # fmt: skip
    add("resize 50% + caption + q60", "combo", J(lambda i: caption_bar(scale(i, .5)), 60))
    add("print + re-scan", "combo", J(rescan, 50), "hard")
    return T


# ------------------------------------------------------------------ source photos
def pick_sources(dirs: list[str], n: int, seed: int) -> list[Path]:
    skip_dirs = ("node_modules", ".venv", "site-packages", "AI-INFLUENCED", ".git", "__pycache__")
    cands: list[Path] = []
    for d in dirs:
        for dp, _, fs in os.walk(d):
            if any(s in dp for s in skip_dirs):
                continue
            for f in fs:
                p = Path(dp) / f
                if p.suffix.lower() in (".jpg", ".jpeg") and not SKIP_NAME.search(f) \
                        and 150_000 <= p.stat().st_size <= 8_000_000:  # fmt: skip
                    cands.append(p)
    random.Random(seed).shuffle(cands)
    chosen, seen_sha, hashes = [], set(), []
    for p in cands:
        data = p.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if sha in seen_sha:
            continue
        try:
            im = Image.open(io.BytesIO(data))
            if min(im.size) < 600:
                continue
            h = fp.phash(data)
        except Exception:  # noqa: BLE001
            continue
        if h is None or any(fp.distance(h, o) <= SAME for o in hashes):  # drop real near-duplicates
            continue
        seen_sha.add(sha)
        hashes.append(h)
        chosen.append(p)
        if len(chosen) >= n:
            break
    return chosen


def validated(data: bytes, name: str):
    try:
        return validate_upload(data, name, SETTINGS)
    except ValidationError:
        return None


# ------------------------------------------------------------------ Part A
def part_a(sources: list[Path], work: Path, out: list[str]):
    Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())
    db = new_session()
    T = build_transforms()
    origs = {}
    treated = Counter()
    for i, p in enumerate(sources):
        data = p.read_bytes()
        vf = validated(data, p.name)
        if vf is None:
            continue
        warn: list[str] = []
        kind, ph = _classify(vf, "auto", warn)
        treated[kind] += 1
        origs[i] = (data, vf, kind, ph)
        register(db, application_id=f"orig-{i}", applicant_id=f"O{i}", scheme="", file_name=p.name,
                 part="file", kind=kind, sha256=vf.sha256,
                 phash=fp.to_hex(ph) if ph is not None else None)  # fmt: skip
    out.append(f"## Part A: duplicate detection\n\nSource photos: **{len(origs)}** "
               f"(pipeline treated {treated['photo']} as *photo*, {treated['document']} as *document*). "
               f"Thresholds: same photo <= {SAME}/64, similar <= {SIMILAR}/64.\n")
    doc_idx = {i for i, o in origs.items() if o[2] == "document"}
    if doc_idx:
        out.append(f"> {len(doc_idx)} real photos were classed as *document* by the layout heuristic, so only "
                   "exact copies of them can ever be matched. These rows are scored separately below.\n")

    stats = defaultdict(lambda: Counter())
    dists = defaultdict(list)
    var_hashes: list[tuple[int, str, int]] = []  # (source idx, transform, phash) of photo-class variants
    for i, (data, vf, kind, ph) in origs.items():
        img = Image.open(io.BytesIO(data))
        img.load()
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        for name, (cat, fn, expect) in T.items():
            try:
                vb = fn(img)
            except Exception:  # noqa: BLE001
                stats[name]["error"] += 1
                continue
            if i == 0 and work:
                (work / f"{name.replace(' ', '_').replace('%', 'pc').replace('+', 'p')}.jpg").write_bytes(vb)
            vvf = validated(vb, f"v{i}.jpg")
            if vvf is None:
                stats[name]["rejected"] += 1
                continue
            warn = []
            vkind, vph = _classify(vvf, "auto", warn)
            sub = Submission("variant", "VAR")
            flags = duplicate_flags(db, vvf, sub, vph, SETTINGS)
            hit = {"high": set(), "review": set()}
            for f in flags:
                for m in f.matches:
                    hit[f.level].add(m["application_id"])
            target = f"orig-{i}"
            others_h = {a for a in hit["high"] if a != target}
            others_r = {a for a in hit["review"] if a != target}
            row = "doc-class" if i in doc_idx else "photo-class"
            if target in hit["high"]:
                res = "high"
            elif target in hit["review"]:
                res = "review"
            elif vkind == "document" and vph is None:
                res = "miss (variant looks like a document)"
            else:
                res = "miss"
            stats[name][f"{row}:{res}"] += 1
            if others_h or others_r:
                stats[name]["WRONG match to another photo"] += 1
            if vph is not None and ph is not None:
                dists[name].append(fp.distance(ph, vph))
                var_hashes.append((i, name, vph))

    # per transform table (photo-class sources only)
    out.append("### Recall per edit (photo-class sources)\n")
    out.append("| Edit | Caught high | Caught review | Missed | Median bit-distance | Wrong match |")
    out.append("|---|---:|---:|---:|---:|---:|")
    tot = Counter()
    cat_tot = defaultdict(Counter)
    for name, (cat, _, expect) in T.items():
        s = stats[name]
        hi, rv = s["photo-class:high"], s["photo-class:review"]
        ms = sum(v for k, v in s.items() if k.startswith("photo-class:miss"))
        n = hi + rv + ms
        if not n:
            continue
        med = statistics.median(dists[name]) if dists[name] else "-"
        out.append(f"| {name} | {hi/n:.0%} | {rv/n:.0%} | {ms/n:.0%} | {med} | {s['WRONG match to another photo']} |")
        for t in (tot, cat_tot[cat]):
            t["hi"] += hi; t["rv"] += rv; t["ms"] += ms  # noqa: E702
    out.append("")
    out.append("### Recall by category\n")
    out.append("| Category | Flagged (high+review) | High only | Missed |")
    out.append("|---|---:|---:|---:|")
    for cat, t in cat_tot.items():
        n = t["hi"] + t["rv"] + t["ms"]
        out.append(f"| {cat} | {(t['hi']+t['rv'])/n:.0%} | {t['hi']/n:.0%} | {t['ms']/n:.0%} |")
    n = tot["hi"] + tot["rv"] + tot["ms"]
    out.append(f"| **all edits** | **{(tot['hi']+tot['rv'])/n:.0%}** | **{tot['hi']/n:.0%}** | **{tot['ms']/n:.0%}** |\n")

    if doc_idx:
        dtot = Counter()
        for name in T:
            for k, v in stats[name].items():
                if k.startswith("doc-class:"):
                    dtot[k.split(":", 1)[1].split(" ")[0]] += v
        out.append(f"Doc-class sources (heuristic called them documents): {dict(dtot)}\n")

    # false positives on unrelated photos
    out.append("### False positives (unrelated photos)\n")
    pids = [i for i, o in origs.items() if o[3] is not None]
    pair = [fp.distance(origs[a][3], origs[b][3]) for ai, a in enumerate(pids) for b in pids[ai + 1:]]
    out.append(f"* Original vs original pairs: **{len(pair)}**. Closest pair: **{min(pair)}**/64, "
               f"median **{statistics.median(pair)}**/64.")
    out.append(f"* Pairs <= {SAME} (would be 'same photo'): **{sum(d <= SAME for d in pair)}**; "
               f"<= {SIMILAR} (would be 'similar'): **{sum(d <= SIMILAR for d in pair)}**.")
    cross = [fp.distance(vh, origs[j][3]) for (i, _, vh) in var_hashes for j in pids if j != i]
    out.append(f"* Edited copy vs a *different* original: **{len(cross)}** comparisons, "
               f"<= {SAME}: **{sum(d <= SAME for d in cross)}** ({sum(d <= SAME for d in cross)/len(cross):.3%}), "
               f"<= {SIMILAR}: **{sum(d <= SIMILAR for d in cross)}** ({sum(d <= SIMILAR for d in cross)/len(cross):.3%}).\n")

    # threshold sweep (photo-class, "catch" edits)
    out.append("### Threshold sweep\n")
    out.append("Recall = share of edited copies (all edits except rotate/mirror/re-scan) within the distance of "
               "their own original. False-positive rate = share of edited-copy-vs-different-photo pairs within it.\n")
    out.append("| Distance <= | Recall | False-positive rate |")
    out.append("|---:|---:|---:|")
    own = []
    for name, (cat, _, expect) in T.items():
        if expect == "catch":
            own += dists[name]
    for t in (4, 6, 8, 10, 12, 14, 16, 18, 20, 24):
        out.append(f"| {t} | {sum(d <= t for d in own)/len(own):.1%} | {sum(d <= t for d in cross)/len(cross):.3%} |")
    out.append("")
    return origs


# ------------------------------------------------------------------ Part B
def exif_bytes(**tags) -> Image.Image.Exif:
    ex = Image.Exif()
    ids = {"Software": 305, "Artist": 315, "ImageDescription": 270, "Make": 271, "Model": 272}
    for k, v in tags.items():
        ex[ids[k]] = v
    return ex


def xmp(creator_tool: str = "", source_type: str = "") -> bytes:
    body = ""
    if creator_tool:
        body += f"<xmp:CreatorTool>{creator_tool}</xmp:CreatorTool>"
    if source_type:
        body += f"<Iptc4xmpExt:DigitalSourceType>http://cv.iptc.org/newscodes/digitalsourcetype/{source_type}" \
                "</Iptc4xmpExt:DigitalSourceType>"
    return (
        '<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?><x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description xmlns:xmp="http://ns.adobe.com/xap/1.0/" '
        'xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-12/">'
        f"{body}</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end='w'?>"
    ).encode()


def flagged(data: bytes, name: str) -> tuple[str, list[str]]:
    vf = validated(data, name)
    if vf is None:
        return "rejected", []
    r = ai_check(vf, SETTINGS)
    return r.level, [f.code for f in r.flags]


def part_b(sources: list[Path], origs, ai_dir: str | None, out: list[str]):
    out.append("## Part B: AI-influence metadata\n")

    # B1 real files -> false positives
    codes = Counter()
    lv = Counter()
    for p in sources:
        level, cs = flagged(p.read_bytes(), p.name)
        lv[level] += 1
        codes.update(cs or ["(no flags)"])
    out.append("### B1. Real, non-AI files from this machine (should all be `none`)\n")
    out.append(f"{len(sources)} files -> {dict(lv)}; flag codes seen: {dict(codes)}\n")

    # base images
    bases = []
    for p in sources[:8]:
        im = Image.open(p)
        im.load()
        bases.append(long_edge(im.convert("RGB"), 1536))
    ai_tools = ["Midjourney", "Midjourney v6.1", "Stable Diffusion XL", "DALL-E 3", "DALL·E 2", "Adobe Firefly",
                "Google Gemini", "ChatGPT", "Leonardo.Ai", "ComfyUI", "NovelAI", "Ideogram", "Flux.1 dev",
                "Bing Image Creator", "Fooocus", "Imagen 3", "Copilot Designer", "Runway ML"]  # fmt: skip
    edit_tools = ["Adobe Photoshop 26.0", "Canva", "Picsart", "Snapseed 2.0", "Lightroom Classic", "GIMP 2.10",
                  "Facetune", "Remini"]  # fmt: skip

    def rate(label, cases, want):
        got = Counter()
        miss = []
        for lbl, data in cases:
            level, cs = flagged(data, "t.jpg" if not lbl.startswith("PNG") else "t.png")
            got[level] += 1
            if level not in want:
                miss.append(lbl)
        n = sum(got.values())
        ok = sum(got[w] for w in want)
        out.append(f"| {label} | {n} | {ok}/{n} ({ok/n:.0%}) | {dict(got)} | {', '.join(miss[:6]) or '-'} |")

    out.append("### B2. Injected tags (images are real photos; tag added)\n")
    out.append("| Case | n | Detected as expected | Levels | Missed |")
    out.append("|---|---:|---:|---|---|")
    b = bases[0]
    rate("EXIF Software = AI tool", [(t, enc(b, "JPEG", 92, exif=exif_bytes(Software=t))) for t in ai_tools],
         ("review", "high"))  # fmt: skip
    rate("EXIF Artist = AI tool", [(t, enc(b, "JPEG", 92, exif=exif_bytes(Artist=t))) for t in ai_tools],
         ("review", "high"))  # fmt: skip
    rate("EXIF ImageDescription 'made with X'",
         [(t, enc(b, "JPEG", 92, exif=exif_bytes(ImageDescription=f"Image made with {t}"))) for t in ai_tools],
         ("review", "high"))  # fmt: skip
    rate("XMP CreatorTool = AI tool",
         [(t, enc(b, "JPEG", 92, xmp=xmp(creator_tool=t))) for t in ai_tools], ("review", "high"))  # fmt: skip
    rate("XMP DigitalSourceType trainedAlgorithmicMedia",
         [("tam", enc(b, "JPEG", 92, xmp=xmp(source_type="trainedAlgorithmicMedia"))),
          ("composite", enc(b, "JPEG", 92, xmp=xmp(source_type="compositeWithTrainedAlgorithmicMedia")))],
         ("review", "high"))  # fmt: skip

    def png_with(**text):
        info = PngImagePlugin.PngInfo()
        for k, v in text.items():
            info.add_text(k, v)
        return enc(b, "PNG", pnginfo=info)

    sd = "a red barn, masterpiece\nNegative prompt: blurry\nSteps: 28, Sampler: Euler a, CFG scale: 7, Seed: 1234"
    rate("PNG text (SD / Comfy / Invoke keys)",
         [("PNG parameters", png_with(parameters=sd)), ("PNG prompt", png_with(prompt='{"3":{"class_type":"KSampler"}}')),
          ("PNG workflow", png_with(workflow="{}")), ("PNG invokeai", png_with(invokeai_metadata="{}")),
          ("PNG Software NovelAI", png_with(Software="NovelAI")), ("PNG Comment Midjourney", png_with(Comment="Midjourney"))],
         ("review", "high"))  # fmt: skip
    rate("Editing software only (expect `none`, info note)",
         [(t, enc(b, "JPEG", 92, exif=exif_bytes(Software=t))) for t in edit_tools], ("none",))  # fmt: skip

    # B3 survival
    out.append("")
    out.append("### B3. Does the AI tag survive edits? (EXIF `Software = Midjourney`)\n")
    out.append("`strip` = the editing app drops metadata (Pillow default, WhatsApp, screenshots). "
               "`keep` = the app copies EXIF across.\n")
    out.append("| Edit | Detected if metadata stripped | Detected if metadata kept |")
    out.append("|---|---|---|")
    ex = exif_bytes(Software="Midjourney")
    base = bases[1]
    edits = {
        "none (straight from tool)": lambda i: i,
        "re-save jpeg q70": lambda i: i,
        "resize 50%": lambda i: scale(i, .5),
        "crop 90%": lambda i: crop_c(i, .9),
        "brightness +30%": lambda i: ImageEnhance.Brightness(i).enhance(1.3),
        "WhatsApp (1600px q70)": lambda i: long_edge(i, 1600),
    }
    for name, fn in edits.items():
        q = 70 if "q70" in name or "WhatsApp" in name else 92
        stripped = flagged(enc(fn(base), "JPEG", q), "t.jpg")[0]
        kept = flagged(enc(fn(base), "JPEG", q, exif=ex), "t.jpg")[0]
        out.append(f"| {name} | {stripped} | {kept} |")
    shot = phone_screenshot(base)
    out.append(f"| phone screenshot (PNG) | {flagged(enc(shot, 'PNG'), 't.png')[0]} | n/a (screenshots carry no EXIF) |")
    out.append("")

    # B4 C2PA
    out.append("### B4. Signed C2PA credential (test-signed sample)\n")
    c2 = ROOT / "tests" / "samples" / "c2pa_ai.jpg"
    out.append("| Case | Result | Flags |")
    out.append("|---|---|---|")
    if c2.exists():
        raw = c2.read_bytes()
        img = Image.open(io.BytesIO(raw))
        img.load()

        def row(label, data, nm="t.jpg"):
            lvl, cs = flagged(data, nm)
            out.append(f"| {label} | {lvl} | {', '.join(cs) or '-'} |")

        row("file straight from the AI tool", raw)
        row("renamed .png (content is jpeg)", raw, "t.png")
        row("re-saved with Pillow (drops credential)", enc(img, "JPEG", 92))
        row("resized 50%", enc(scale(img, .5), "JPEG", 85))
        row("WhatsApp style (1600px q70)", enc(long_edge(img, 1600), "JPEG", 70))
        row("converted to PNG", enc(img, "PNG"), "t.png")
        row("phone screenshot", enc(phone_screenshot(img), "PNG"), "t.png")
        # tamper: flip one byte in the middle of the image data, keep the manifest
        mid = bytearray(raw)
        pos = len(mid) // 2
        mid[pos] ^= 0xFF
        row("one pixel-data byte flipped after signing (tamper)", bytes(mid))
        row("manifest cut off (truncated file)", raw[: int(len(raw) * 0.6)])
    else:
        out.append("| (sample missing) | - | - |")
    out.append("")

    # B5 documents
    out.append("### B5. PDF and DOCX metadata\n")
    out.append("| Case | Result | Flags |")
    out.append("|---|---|---|")
    try:
        from pypdf import PdfWriter

        def pdf(producer, creator=""):
            w = PdfWriter()
            w.add_blank_page(300, 300)
            w.add_metadata({"/Producer": producer, "/Creator": creator or producer})
            buf = io.BytesIO()
            w.write(buf)
            return buf.getvalue()

        for label, prod in [("PDF Producer = Adobe Firefly", "Adobe Firefly"), ("PDF Producer = ChatGPT", "ChatGPT"),
                            ("PDF Producer = Microsoft Word", "Microsoft Word"),
                            ("PDF Producer = Canva", "Canva"), ("PDF Producer = iLovePDF", "iLovePDF")]:
            lvl, cs = flagged(pdf(prod), "t.pdf")
            out.append(f"| {label} | {lvl} | {', '.join(cs) or '-'} |")
    except Exception as exc:  # noqa: BLE001
        out.append(f"| PDF cases skipped ({exc}) | - | - |")
    sample_docx = ROOT / "tests" / "samples" / "sample.docx"
    if sample_docx.exists():
        def docx(creator):
            zin = zipfile.ZipFile(sample_docx)
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    d = zin.read(item.filename)
                    if item.filename == "docProps/core.xml":
                        d = re.sub(rb"<dc:creator>.*?</dc:creator>", f"<dc:creator>{creator}</dc:creator>".encode(), d)
                    zout.writestr(item, d)
            return buf.getvalue()

        for creator in ("ChatGPT", "John Smith"):
            lvl, cs = flagged(docx(creator), "t.docx")
            out.append(f"| DOCX creator = {creator} | {lvl} | {', '.join(cs) or '-'} |")
    out.append("")

    # B6 real AI images supplied by the user
    if ai_dir and Path(ai_dir).is_dir():
        out.append(f"### B6. Real AI-generated images supplied in `{Path(ai_dir).name}`\n")
        out.append("| File | Result | Flags |")
        out.append("|---|---|---|")
        for p in sorted(Path(ai_dir).iterdir()):
            if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".pdf"):
                lvl, cs = flagged(p.read_bytes(), p.name)
                out.append(f"| {p.name} | {lvl} | {', '.join(cs) or '-'} |")
        out.append("")
    else:
        out.append("### B6. Real AI images\n\n**Not tested.** No genuine ChatGPT / Gemini / Firefly / Midjourney "
                   "files were available. Re-run with `--ai-dir <folder of real AI images>`.\n")


# ------------------------------------------------------------------ Part C
def part_c(sources: list[Path], out: list[str]):
    out.append("## Part C: false-positive probes (innocent metadata that contains an AI-marker word)\n")
    out.append("| Metadata text | Result | Why it is innocent |")
    out.append("|---|---|---|")
    probes = [
        ("Artist", "Gemini Photo Studio", "a business name"),
        ("Artist", "Dalle Nogare", "a surname"),
        ("Artist", "Rajesh Dallesandro", "a surname containing 'dalle'"),
        ("ImageDescription", "Visit to the OpenAI office, Mumbai", "a caption about a place"),
        ("ImageDescription", "Photo of the Gemini constellation", "astronomy"),
        ("ImageDescription", "ideogram of Chinese character 'tree'", "linguistics"),
        ("ImageDescription", "Flooded road near Fooocus Hotel", "contrived name"),
        ("Software", "Samsung SM-S918B", "phone firmware"),
        ("Software", "Google Pixel 8 Pro", "phone firmware"),
        ("Software", "Windows Photo Editor 10", "OS viewer"),
        ("Software", "Microsoft Photos", "OS viewer"),
        ("Software", "Adobe Lightroom Mobile", "plain edit, not AI"),
    ]
    b = Image.open(sources[0]).convert("RGB")
    b = long_edge(b, 800)
    for tag, val, why in probes:
        lvl, cs = flagged(enc(b, "JPEG", 90, exif=exif_bytes(**{tag: val})), "t.jpg")
        out.append(f"| {tag} = {val} | {lvl} | {why} |")
    info = PngImagePlugin.PngInfo()
    info.add_text("prompt", "Please enter your name")
    lvl, _ = flagged(enc(b, "PNG", pnginfo=info), "t.png")
    out.append(f"| PNG text key `prompt` = 'Please enter your name' | {lvl} | generic key used by non-AI tools |")
    info = PngImagePlugin.PngInfo()
    info.add_text("Description", "Screenshot taken with Snipping Tool")
    lvl, _ = flagged(enc(b, "PNG", pnginfo=info), "t.png")
    out.append(f"| PNG Description = 'Screenshot taken with Snipping Tool' | {lvl} | screenshot tool |")
    out.append("")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", nargs="+", required=True, help="folders to pick real photos from")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=str(ROOT / "eval" / "report.md"))
    ap.add_argument("--work", default="", help="folder to keep one sample set of edited copies")
    ap.add_argument("--ai-dir", default=None, help="folder of genuine AI-generated images to test")
    a = ap.parse_args()

    work = Path(a.work) if a.work else Path(tempfile.mkdtemp(prefix="aci_eval_"))
    work.mkdir(parents=True, exist_ok=True)
    sources = pick_sources(a.src, a.n, a.seed)
    if len(sources) < 5:
        sys.exit(f"Only {len(sources)} usable photos found. Point --src at a folder with real photos.")
    out = ["# Accuracy report", "", f"Sources sampled: {len(sources)} photos (seed {a.seed}). "
           "Edited copies of the first photo are in the work folder for eyeballing.", ""]
    origs = part_a(sources, work, out)
    part_b(sources, origs, a.ai_dir, out)
    part_c(sources, out)
    Path(a.out).write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))
    print(f"\nReport: {a.out}\nSample edits: {work}")


if __name__ == "__main__":
    main()
