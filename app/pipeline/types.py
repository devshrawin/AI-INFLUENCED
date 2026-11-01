"""Plain data classes passed between pipeline steps.

Scores are always percentages 0-100 where 100 = "looks AI-generated".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Signal:
    """One piece of evidence shown on the result screen."""

    name: str  # human-readable, e.g. "Image model (SwinV2)"
    source: str  # provenance | metadata | image_model | text_model
    score: float | None  # 0-100, None = informational only
    weight: float = 0.0  # weight used by the combiner (filled in by combine.py)
    model_id: str | None = None
    model_version: str | None = None
    detail: str = ""
    target: str = "file"  # which part: "file", "text", "image 2", ...
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProvenanceResult:
    """Outcome of the C2PA + metadata checks for one file or image."""

    c2pa_present: bool = False
    c2pa_state: str | None = None  # Valid | Trusted | Invalid | None
    c2pa_signer: str | None = None
    c2pa_trusted: bool = False
    ai_declared: bool = False  # C2PA says "made/edited with generative AI"
    ai_declared_type: str | None = None  # e.g. trainedAlgorithmicMedia
    generator: str | None = None  # tool name from the credential
    confirmed_ai: bool = False  # valid C2PA AI declaration -> overrides models
    # Weak, unsigned metadata hints (EXIF/XMP/PNG text/PDF producer...)
    ai_hints: list[str] = field(default_factory=list)
    camera_hints: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractedDocument:
    text: str
    images: list[bytes]  # raw bytes of embedded images (JPEG/PNG/...)
    metadata: dict[str, str]
    notes: list[str] = field(default_factory=list)
