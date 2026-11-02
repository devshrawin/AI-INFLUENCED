"""Checks one uploaded file of an application and returns its flags.

Two checks only:
  1. AI influence from metadata
       - signed C2PA content credential declaring generative AI  -> high
       - credential present but signature broken                   -> review
       - unsigned metadata naming an AI tool (EXIF/XMP/PNG/PDF)    -> review
       - saved by editing software (Photoshop, Canva...)           -> info
  2. Same image / file uploaded before by another applicant
       - identical file (SHA-256), any type                        -> high
       - same photo, even resized/compressed/lightly cropped       -> high
       - very similar photo                                        -> review
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.pipeline import duplicates, fingerprint
from app.pipeline.extract import extract_document
from app.pipeline.flags import DISCLAIMER, HIGH, INFO, REVIEW, Flag, build_note, overall_level
from app.pipeline.provenance import AI_SOURCE_TYPES, check_document_metadata, check_provenance
from app.pipeline.types import ProvenanceResult
from app.pipeline.validate import ValidatedFile

log = logging.getLogger(__name__)

DOC_TYPES = ("auto", "photo", "document")


@dataclass
class Submission:
    """Who uploaded the file. Comes from the scheme platform."""

    application_id: str
    applicant_id: str
    scheme: str = ""
    doc_type: str = "auto"  # auto | photo | document


@dataclass
class CheckResult:
    application_id: str
    applicant_id: str
    scheme: str
    filename: str
    sha256: str
    file_type: str  # pdf, docx, jpeg, png, webp
    treated_as: str  # photo | document
    size: int
    level: str  # high | review | none
    note: str
    flags: list[Flag]
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    av_status: str = "not_scanned"
    duration_s: float = 0.0
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("metadata")  # can be large; available in the UI
        return d


# ----------------------------------------------------------------- metadata flags
def provenance_flags(prov: ProvenanceResult, target: str) -> list[Flag]:
    flags: list[Flag] = []
    if prov.confirmed_ai:
        what = AI_SOURCE_TYPES.get(prov.ai_declared_type or "", "made with generative AI")
        trust = "" if prov.c2pa_trusted else " The signer is not on the local trust list."
        flags.append(Flag(
            "AI_CREDENTIAL", HIGH,
            f"A digitally signed content credential says this image was {what}"
            f" (tool: {prov.generator or 'not named'}).{trust}",
            target,
        ))  # fmt: skip
    elif prov.ai_declared:
        flags.append(Flag(
            "AI_CREDENTIAL_BROKEN", REVIEW,
            "A content credential claims AI involvement, but its signature is broken "
            "(the file was changed after signing).", target,
        ))  # fmt: skip
    elif prov.c2pa_present and prov.c2pa_state not in ("Valid", "Trusted"):
        flags.append(Flag(
            "CREDENTIAL_BROKEN", REVIEW,
            "The file carries a content credential whose signature is broken "
            "(the file was changed after it was signed).", target,
        ))  # fmt: skip
    elif prov.c2pa_present:
        msg = f"Signed content credential present, no AI declared (signer: {prov.c2pa_signer})."
        flags.append(Flag("CREDENTIAL_OK", INFO, msg, target))
    if prov.ai_hints and not prov.confirmed_ai:
        flags.append(Flag(
            "AI_METADATA", REVIEW,
            "File information names an AI tool: " + "; ".join(prov.ai_hints[:3])
            + ". (Not signed: it can be added or removed by anyone.)", target,
        ))  # fmt: skip
    if prov.edit_hints:
        msg = "Saved by editing software: " + "; ".join(prov.edit_hints[:3]) + "."
        flags.append(Flag("EDITING_SOFTWARE", INFO, msg, target))
    return flags


# ----------------------------------------------------------------- duplicate flags
def _list(matches: list[duplicates.Match]) -> str:
    ids = ", ".join(m.application_id for m in matches[:5])
    more = f" and {len(matches) - 5} more" if len(matches) > 5 else ""
    return ids + more


def duplicate_flags(db: Session, vf: ValidatedFile, sub: Submission, phash: int | None,
                    settings: Settings) -> list[Flag]:  # fmt: skip
    flags: list[Flag] = []
    exact = duplicates.exact_matches(db, vf.sha256, sub.applicant_id)
    if exact:
        n = len(exact)
        flags.append(Flag(
            "DUPLICATE_FILE", HIGH,
            f"This exact file was already uploaded in {n} other application{'s' if n > 1 else ''} "
            f"by a different applicant: {_list(exact)}.",
            matches=[m.to_dict() for m in exact[: duplicates.MAX_LISTED]],
        ))  # fmt: skip
    if phash is not None:
        similar = duplicates.photo_matches(
            db, phash, sub.applicant_id, settings.similar_photo_max_distance, vf.sha256
        )
        exact_apps = {m.application_id for m in exact}
        similar = [m for m in similar if m.application_id not in exact_apps]
        same = [m for m in similar if m.distance <= settings.same_photo_max_distance]
        close = [m for m in similar if m.distance > settings.same_photo_max_distance]
        if same:
            flags.append(Flag(
                "DUPLICATE_PHOTO", HIGH,
                f"The same photo (possibly resized, compressed or cropped) was already uploaded in "
                f"{len(same)} other application{'s' if len(same) > 1 else ''} by a different applicant: "
                f"{_list(same)}.",
                matches=[m.to_dict() for m in same[: duplicates.MAX_LISTED]],
            ))  # fmt: skip
        if close:
            flags.append(Flag(
                "SIMILAR_PHOTO", REVIEW,
                f"A very similar photo was uploaded in {len(close)} other "
                f"application{'s' if len(close) > 1 else ''}: {_list(close)}. "
                "It may be the same scene photographed again, or an edited copy.",
                matches=[m.to_dict() for m in close[: duplicates.MAX_LISTED]],
            ))  # fmt: skip
    return flags


# ----------------------------------------------------------------- shared steps
def _metadata_flags(vf: ValidatedFile, settings: Settings) -> tuple[list[Flag], dict[str, str], list[str]]:
    """AI-influence flags from the file's metadata (and, for documents, embedded images)."""
    trust = settings.c2pa_trust_anchors_file
    prov, meta = check_provenance(vf.data, vf.mime, trust)
    flags = provenance_flags(prov, "file")
    notes: list[str] = []
    if not vf.is_image:
        doc = extract_document(vf.kind, vf.data, settings.max_embedded_images)
        notes += doc.notes
        meta.update({f"Doc:{k}": v for k, v in doc.metadata.items()})
        doc_prov = ProvenanceResult()
        check_document_metadata(doc.metadata, doc_prov)
        flags += provenance_flags(doc_prov, "document information")
        for i, blob in enumerate(doc.images, start=1):
            mime = "image/png" if blob[:4] == b"\x89PNG" else "image/jpeg"
            img_prov, _ = check_provenance(blob, mime, trust)
            flags += provenance_flags(img_prov, f"embedded image {i}")
    return flags, meta, notes


def _classify(vf: ValidatedFile, doc_type: str, warnings: list[str]) -> tuple[str, int | None]:
    """Decide photo vs document and fingerprint photos. Returns (treated_as, phash)."""
    if not vf.is_image:
        return "document", None
    if doc_type in ("photo", "document"):
        treated_as = doc_type
    else:
        treated_as = "document" if fingerprint.looks_like_document(vf.data) else "photo"
    phash: int | None = None
    if treated_as == "photo":
        phash = fingerprint.phash(vf.data)
        if phash is None:
            warnings.append("The image is almost blank, so it was not compared with other photos.")
    else:
        warnings.append(
            "Treated as a document (scan or photo of paper): only exact copies of the same file "
            "are detected, because different documents with the same printed layout look alike."
        )
    return treated_as, phash


# ----------------------------------------------------------------- PoC entry points
@dataclass
class PartialResult:
    """Result of a single check (AI only, or duplicates only) for the PoC page."""

    filename: str
    sha256: str
    file_type: str
    size: int
    level: str
    flags: list[Flag]
    treated_as: str = ""
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


def ai_check(vf: ValidatedFile, settings: Settings | None = None) -> PartialResult:
    """AI influence from metadata only. Stores nothing."""
    settings = settings or get_settings()
    flags, meta, notes = _metadata_flags(vf, settings)
    return PartialResult(vf.filename, vf.sha256, vf.kind, vf.size, overall_level(flags), flags,
                         warnings=notes, metadata=meta)  # fmt: skip


def duplicate_check(vf: ValidatedFile, sub: Submission, db: Session, settings: Settings | None = None
                    ) -> PartialResult:  # fmt: skip
    """Compare with all earlier uploads from other applicants, then remember this one."""
    settings = settings or get_settings()
    warnings: list[str] = []
    treated_as, phash = _classify(vf, sub.doc_type, warnings)
    flags = duplicate_flags(db, vf, sub, phash, settings)
    duplicates.register(
        db, application_id=sub.application_id, applicant_id=sub.applicant_id, scheme=sub.scheme,
        file_name=vf.filename, part="file", kind=treated_as, sha256=vf.sha256,
        phash=fingerprint.to_hex(phash) if phash is not None else None,
    )  # fmt: skip
    return PartialResult(vf.filename, vf.sha256, vf.kind, vf.size, overall_level(flags), flags,
                         treated_as=treated_as, warnings=warnings)  # fmt: skip


# ----------------------------------------------------------------- main entry
def check_file(
    vf: ValidatedFile, sub: Submission, db: Session, settings: Settings | None = None
) -> CheckResult:
    settings = settings or get_settings()
    started = time.monotonic()
    flags, meta, warnings = _metadata_flags(vf, settings)
    treated_as, phash = _classify(vf, sub.doc_type, warnings)
    flags += duplicate_flags(db, vf, sub, phash, settings)
    duplicates.register(
        db,
        application_id=sub.application_id,
        applicant_id=sub.applicant_id,
        scheme=sub.scheme,
        file_name=vf.filename,
        part="file",
        kind=treated_as,
        sha256=vf.sha256,
        phash=fingerprint.to_hex(phash) if phash is not None else None,
    )

    return CheckResult(
        application_id=sub.application_id,
        applicant_id=sub.applicant_id,
        scheme=sub.scheme,
        filename=vf.filename,
        sha256=vf.sha256,
        file_type=vf.kind,
        treated_as=treated_as,
        size=vf.size,
        level=overall_level(flags),
        note=build_note(flags),
        flags=flags,
        warnings=warnings,
        metadata=meta,
        av_status=vf.av_status,
        duration_s=round(time.monotonic() - started, 3),
    )
