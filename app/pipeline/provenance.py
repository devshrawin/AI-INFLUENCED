"""Step 3: provenance — C2PA content credentials and file metadata.

Two kinds of evidence:

* **C2PA content credentials** are cryptographically signed. If a credential
  with an intact signature says the content was created by generative AI
  (IPTC digital source type "trainedAlgorithmicMedia" or similar), we mark
  the file "AI (provenance-confirmed)".
* **Metadata hints** (EXIF Software, XMP, PNG text chunks, PDF Producer…) are
  NOT signed and are trivially edited or stripped. They only nudge the score.

All reading is local. Remote manifest fetching and OCSP lookups in the C2PA
library are switched off.
"""

from __future__ import annotations

import io
import json
import logging
import re
import shutil
import subprocess
from pathlib import Path

from PIL import ExifTags, Image

from app.pipeline.types import ProvenanceResult

log = logging.getLogger(__name__)

# IPTC digital source types meaning "generative AI was involved".
AI_SOURCE_TYPES = {
    "trainedAlgorithmicMedia": "fully AI-generated",
    "compositeWithTrainedAlgorithmicMedia": "edited/composited with generative AI",
    "compositeSynthetic": "composite including synthetic elements",
}

# Lower-case substrings in metadata that point to a known AI generator.
AI_GENERATOR_MARKERS = [
    "midjourney", "dall-e", "dall·e", "dalle", "stable diffusion", "stablediffusion", "sdxl",
    "comfyui", "automatic1111", "novelai", "adobe firefly", "google imagen", "gemini", "openai", "chatgpt",
    "gpt-4", "flux.1", "black forest labs", "leonardo.ai", "ideogram", "runwayml", "made with google ai",
    "bing image creator", "copilot designer", "dreamstudio", "invokeai", "fooocus",
    "trainedalgorithmicmedia",
]  # fmt: skip
# PNG text keys written by popular local generators.
AI_PNG_KEYS = {"parameters", "prompt", "workflow", "sd-metadata", "invokeai_metadata", "dream"}

_XMP_RE = re.compile(rb"<x:xmpmeta.*?</x:xmpmeta>", re.S)


# --------------------------------------------------------------------------- C2PA
def _c2pa_context(trust_anchors_pem: str | None):
    import c2pa

    cfg: dict = {"verify": {"remote_manifest_fetch": False, "ocsp_fetch": False}}
    if trust_anchors_pem:
        cfg["trust"] = {"trust_anchors": trust_anchors_pem}
    return c2pa.Context(c2pa.Settings.from_dict(cfg))


def read_c2pa(data: bytes, mime: str, result: ProvenanceResult, trust_anchors_pem: str | None = None) -> None:
    """Fill the C2PA fields of `result` (in place)."""
    try:
        import c2pa
    except ImportError:  # library missing -> skip, but say so
        result.notes.append("C2PA library not installed; content credentials not checked.")
        return
    try:
        supported = set(c2pa.Reader.get_supported_mime_types())
    except Exception:
        supported = set()
    if supported and mime not in supported:
        return  # format cannot carry C2PA (e.g. plain text)
    try:
        reader = c2pa.Reader.try_create(mime, io.BytesIO(data), context=_c2pa_context(trust_anchors_pem))
    except Exception as exc:  # corrupt / unsupported manifest
        result.c2pa_present = True
        result.c2pa_state = "Invalid"
        result.notes.append(f"C2PA data present but unreadable: {exc}")
        return
    if reader is None:
        return
    with reader:
        result.c2pa_present = True
        result.c2pa_state = reader.get_validation_state()
        store = json.loads(reader.json())

    active = store.get("manifests", {}).get(store.get("active_manifest", ""), {})
    sig = active.get("signature_info") or {}
    result.c2pa_signer = sig.get("common_name") or sig.get("issuer")
    result.c2pa_trusted = result.c2pa_state == "Trusted"
    gens = active.get("claim_generator_info") or []
    if gens:
        result.generator = " ".join(str(gens[0].get(k, "")) for k in ("name", "version")).strip()

    for assertion in active.get("assertions", []):
        if not str(assertion.get("label", "")).startswith("c2pa.actions"):
            continue
        for action in (assertion.get("data") or {}).get("actions", []):
            src = str(action.get("digitalSourceType", "")).rsplit("/", 1)[-1]
            if src in AI_SOURCE_TYPES:
                result.ai_declared = True
                result.ai_declared_type = src
                agent = action.get("softwareAgent")
                if isinstance(agent, dict) and agent.get("name"):
                    result.generator = agent["name"]
                elif isinstance(agent, str):
                    result.generator = agent

    if result.ai_declared:
        if result.c2pa_state in ("Valid", "Trusted"):
            result.confirmed_ai = True
            trust = "signer is on the trust list" if result.c2pa_trusted else "signer NOT on local trust list"
            result.notes.append(
                f"Signed C2PA credential declares {AI_SOURCE_TYPES[result.ai_declared_type]} "
                f"(tool: {result.generator or 'unknown'}; {trust})."
            )
        else:
            result.notes.append(
                "C2PA credential claims AI, but its signature is INVALID (possibly tampered)."
            )
    elif result.c2pa_present:
        result.notes.append(f"C2PA credential present (state: {result.c2pa_state}); no AI declaration.")


# ----------------------------------------------------------------------- metadata
def _scan_text_for_markers(label: str, text: str, result: ProvenanceResult) -> None:
    low = text.lower()
    for marker in AI_GENERATOR_MARKERS:
        if marker in low:
            hint = f"{label} mentions '{marker}'"
            if hint not in result.ai_hints:
                result.ai_hints.append(hint)


def read_image_metadata(data: bytes, result: ProvenanceResult) -> dict[str, str]:
    """EXIF / PNG text / XMP from Pillow. Returns a flat dict for display."""
    meta: dict[str, str] = {}
    try:
        img = Image.open(io.BytesIO(data))
    except Exception as exc:
        result.notes.append(f"Could not read image metadata: {exc}")
        return meta

    exif = img.getexif()
    for tag_id, value in exif.items():
        name = ExifTags.TAGS.get(tag_id, str(tag_id))
        if isinstance(value, bytes):
            continue
        meta[f"EXIF:{name}"] = str(value)[:300]
    for key in ("Software", "Artist", "ImageDescription", "Make", "Model"):
        if f"EXIF:{key}" in meta:
            _scan_text_for_markers(f"EXIF {key}", meta[f"EXIF:{key}"], result)
    if "EXIF:Make" in meta or "EXIF:Model" in meta:
        cam = " ".join(meta.get(k, "") for k in ("EXIF:Make", "EXIF:Model")).strip()
        result.camera_hints.append(f"Camera: {cam}")

    # PNG tEXt/iTXt chunks (Stable Diffusion UIs store prompts here).
    for key, value in (getattr(img, "text", None) or {}).items():
        meta[f"PNG:{key}"] = str(value)[:300]
        if key.lower() in AI_PNG_KEYS:
            result.ai_hints.append(f"PNG text chunk '{key}' (typical of AI image generators)")
        _scan_text_for_markers(f"PNG text '{key}'", str(value), result)

    match = _XMP_RE.search(data)
    if match:
        xmp = match.group(0).decode("utf-8", "replace")
        meta["XMP"] = xmp[:500]
        _scan_text_for_markers("XMP metadata", xmp, result)
    return meta


def read_exiftool(data: bytes, result: ProvenanceResult) -> dict[str, str]:
    """Optional: richer metadata via the `exiftool` binary if it is installed."""
    exe = shutil.which("exiftool")
    if not exe:
        return {}
    try:
        proc = subprocess.run([exe, "-j", "-G", "-"], input=data, capture_output=True, timeout=20)
        items = json.loads(proc.stdout or b"[{}]")[0]
    except Exception as exc:
        log.warning("exiftool failed: %s", exc)
        return {}
    meta = {
        k: str(v)[:300] for k, v in items.items() if k not in ("SourceFile",) and not k.startswith("File:")
    }
    for key, value in meta.items():
        if any(s in key for s in ("Software", "Creator", "Producer", "DigitalSourceType", "Credit", "Tool")):
            _scan_text_for_markers(key, value, result)
    return meta


def check_document_metadata(metadata: dict[str, str], result: ProvenanceResult) -> None:
    for key, value in metadata.items():
        _scan_text_for_markers(f"Document {key}", value, result)


# ---------------------------------------------------------------------- entry
def check_provenance(
    data: bytes, mime: str, trust_anchors_file: Path | None = None
) -> tuple[ProvenanceResult, dict]:
    """Run all provenance checks on an image or document's raw bytes."""
    result = ProvenanceResult()
    pem = None
    if trust_anchors_file and Path(trust_anchors_file).is_file():
        pem = Path(trust_anchors_file).read_text()
    read_c2pa(data, mime, result, pem)
    meta: dict[str, str] = {}
    if mime.startswith("image/"):
        meta.update(read_image_metadata(data, result))
    meta.update(read_exiftool(data, result))
    return result, meta
