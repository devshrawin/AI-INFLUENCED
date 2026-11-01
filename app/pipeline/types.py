"""Plain data classes passed between pipeline steps."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


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
    confirmed_ai: bool = False  # valid, signed C2PA AI declaration
    # Unsigned metadata hints (EXIF/XMP/PNG text/PDF producer...)
    ai_hints: list[str] = field(default_factory=list)
    edit_hints: list[str] = field(default_factory=list)  # e.g. "saved by Photoshop"
    camera_hints: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractedDocument:
    images: list[bytes]  # raw bytes of embedded images
    metadata: dict[str, str]
    notes: list[str] = field(default_factory=list)
