"""Runs a validated file through every pipeline step and returns one result.

image    -> provenance -> image models                          -> combine
document -> extract -> provenance (file + each embedded image)
                    -> image models (embedded images)
                    -> language check -> chunk -> text models   -> combine
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from app.config import Settings, get_settings
from app.pipeline import combine as cmb
from app.pipeline.chunking import chunk_text
from app.pipeline.detectors.base import ModelUnavailable
from app.pipeline.extract import extract_document
from app.pipeline.language import detect_language
from app.pipeline.provenance import check_document_metadata, check_provenance
from app.pipeline.types import ProvenanceResult, Signal
from app.pipeline.validate import ValidatedFile

log = logging.getLogger(__name__)

DISCLAIMER = "This is an indicator for human review, not proof."

# Limits how many checks run the (memory-hungry) models at the same time.
_inference_slots = threading.BoundedSemaphore(2)


@dataclass
class ChunkScore:
    index: int
    score: float
    words: int
    excerpt: str


@dataclass
class AnalysisResult:
    filename: str
    sha256: str
    kind: str
    size: int
    final_score: float | None
    label: str
    reason: str
    explanation: list[str]
    signals: list[Signal]
    warnings: list[str] = field(default_factory=list)
    chunks: list[ChunkScore] = field(default_factory=list)
    language: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    av_status: str = "not_scanned"
    duration_s: float = 0.0
    disclaimer: str = DISCLAIMER

    def model_versions(self) -> dict[str, str]:
        return {s.model_id: s.model_version for s in self.signals if s.model_id and s.model_version}

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["model_versions"] = self.model_versions()
        return d

    @property
    def top_chunks(self) -> list[ChunkScore]:
        return sorted(self.chunks, key=lambda c: c.score, reverse=True)[:3]


# --------------------------------------------------------------------- helpers
def _run(det, payload, target: str, source: str, warnings: list[str]) -> Signal:
    """Run one detector; on failure return an informational signal + warning."""
    try:
        out = det.predict(payload)
        return Signal(det.name, source, out.score, 0.0, det.model_id, det.version, out.detail, target)
    except ModelUnavailable as exc:
        msg = f"{det.name} unavailable: {exc}"
    except Exception as exc:  # a broken input must not crash the whole check
        log.exception("Detector %s failed", det.name)
        msg = f"{det.name} failed on {target}: {exc}"
    if msg not in warnings:
        warnings.append(msg)
    return Signal(det.name, source, None, 0.0, det.model_id, None, msg, target)


def _score_image(
    data: bytes, target: str, detectors, warnings: list[str]
) -> tuple[float | None, list[Signal]]:
    signals, pairs = [], []
    for det, weight in detectors:
        sig = _run(det, data, target, "image_model", warnings)
        if sig.score is not None:
            sig.weight = weight
            pairs.append((sig.score, weight))
        signals.append(sig)
    return cmb.weighted_mean(pairs), signals


def _provenance_signals(prov: ProvenanceResult, target: str) -> list[Signal]:
    out = []
    if prov.c2pa_present:
        out.append(
            Signal(
                "C2PA content credential",
                "provenance",
                99.0 if prov.confirmed_ai else None,
                detail=" ".join(prov.notes) or f"state: {prov.c2pa_state}",
                target=target,
                extra={"signer": prov.c2pa_signer, "trusted": prov.c2pa_trusted, "generator": prov.generator},
            )
        )
    for hint in prov.ai_hints:
        out.append(Signal("Metadata hint", "metadata", None, detail=hint, target=target))
    for hint in prov.camera_hints:
        out.append(
            Signal("Camera metadata", "metadata", None, detail=f"{hint} (easily faked)", target=target)
        )
    return out


def _reason(result: AnalysisResult) -> str:
    if result.label == cmb.LABEL_PROVENANCE:
        return "A signed content credential (C2PA) states this was made with generative AI."
    if result.final_score is None:
        return "No detector could produce a reliable score for this file."
    scored = [s for s in result.signals if s.score is not None and s.weight > 0]
    if not scored:
        return result.explanation[0] if result.explanation else ""
    top = max(scored, key=lambda s: s.score)
    low = min(scored, key=lambda s: s.score)
    if result.label == cmb.LABEL_AI:
        return f"Strongest AI signal: {top.name} on {top.target} ({top.score:.0f}%)."
    if result.label == cmb.LABEL_HUMAN:
        return f"Detectors mostly see human-like patterns (highest: {top.name}, {top.score:.0f}%)."
    if top is low:
        return f"{top.name} gives a borderline {top.score:.0f}%."
    return (
        f"Mixed signals: {top.name} on {top.target} says {top.score:.0f}%, "
        f"{low.name} on {low.target} says {low.score:.0f}%."
    )


# --------------------------------------------------------------------- main entry
def analyze(
    vf: ValidatedFile,
    settings: Settings | None = None,
    image_dets: list | None = None,
    text_dets: list | None = None,
) -> AnalysisResult:
    """Analyse one validated file. Detector lists can be injected for tests."""
    from app.pipeline.detectors import registry

    settings = settings or get_settings()
    image_dets = registry.image_detectors() if image_dets is None else image_dets
    text_dets = registry.text_detectors() if text_dets is None else text_dets
    started = time.monotonic()
    warnings: list[str] = []
    signals: list[Signal] = []
    parts: list[cmb.Part] = []
    chunks: list[ChunkScore] = []
    language = None
    trust = settings.c2pa_trust_anchors_file

    with _inference_slots:
        prov, meta = check_provenance(vf.data, vf.mime, trust)
        confirmed, confirmed_where = prov.confirmed_ai, "file"
        ai_hints = list(prov.ai_hints)
        signals += _provenance_signals(prov, "file")

        if vf.is_image:
            score, sigs = _score_image(vf.data, "image", image_dets, warnings)
            signals += sigs
            if score is not None:
                parts.append(cmb.Part("Image", score, 1.0))
        else:
            doc = extract_document(vf.kind, vf.data, settings.max_embedded_images, settings.max_text_chars)
            warnings += doc.notes
            meta.update({f"Doc:{k}": v for k, v in doc.metadata.items()})
            check_document_metadata(doc.metadata, prov)
            ai_hints = list(prov.ai_hints)
            signals += [
                Signal("Metadata hint", "metadata", None, detail=h, target="document") for h in prov.ai_hints
            ]

            # --- embedded images
            img_scores = []
            for i, blob in enumerate(doc.images, start=1):
                target = f"embedded image {i}"
                iprov, _ = check_provenance(
                    blob, "image/png" if blob[:4] == b"\x89PNG" else "image/jpeg", trust
                )
                signals += _provenance_signals(iprov, target)
                ai_hints += iprov.ai_hints
                if iprov.confirmed_ai and not confirmed:
                    confirmed, confirmed_where = True, target
                score, sigs = _score_image(blob, target, image_dets, warnings)
                signals += sigs
                if score is not None:
                    img_scores.append(score)
            if img_scores:
                # The most AI-like image matters most; average with the mean so
                # one decorative image does not dominate.
                img_part = (max(img_scores) + sum(img_scores) / len(img_scores)) / 2
                parts.append(
                    cmb.Part(
                        f"Embedded images ({len(img_scores)})", img_part, settings.weight_document_images
                    )
                )

            # --- text
            words = len(doc.text.split())
            if words == 0:
                warnings.append("No text found in the document.")
            elif words < settings.min_words_for_text_score:
                warnings.append(
                    f"Only {words} words of text; at least "
                    f"{settings.min_words_for_text_score} are needed for a text score."
                )
            elif text_dets:
                lang = detect_language(doc.text)
                language = asdict(lang)
                if lang.warning:
                    warnings.append(lang.warning)
                pieces = chunk_text(
                    doc.text, settings.chunk_tokens, settings.max_chunks, settings.min_words_for_text_score
                )
                if words > sum(c.word_count for c in pieces):
                    warnings.append(f"Long text: only the first {len(pieces)} sections were scored.")
                per_det: dict[str, list[tuple[float, float]]] = {}
                det_meta: dict[str, tuple] = {}
                for piece in pieces:
                    chunk_pairs = []
                    for det, weight in text_dets:
                        sig = _run(det, piece.text, f"section {piece.index + 1}", "text_model", warnings)
                        det_meta[det.name] = (det, weight, sig)
                        if sig.score is not None:
                            per_det.setdefault(det.name, []).append((sig.score, piece.word_count))
                            chunk_pairs.append((sig.score, weight))
                    cs = cmb.weighted_mean(chunk_pairs)
                    if cs is not None:
                        excerpt = piece.text[:220] + ("…" if len(piece.text) > 220 else "")
                        chunks.append(ChunkScore(piece.index + 1, round(cs, 1), piece.word_count, excerpt))
                # One summary signal per text detector (word-weighted over sections).
                text_pairs = []
                for name, (det, weight, last_sig) in det_meta.items():
                    vals = per_det.get(name)
                    if not vals:
                        signals.append(last_sig)  # carries the error message
                        continue
                    avg = cmb.weighted_mean(vals)
                    w = weight if lang.is_english else 0.0
                    signals.append(
                        Signal(
                            name, "text_model", round(avg, 1), w, det.model_id, det.version,
                            f"average over {len(vals)} section(s)" + ("" if lang.is_english else
                            "; NOT used for the label (non-English text)"), "text",
                        )
                    )  # fmt: skip
                    text_pairs.append((avg, weight))
                text_score = cmb.weighted_mean(text_pairs)
                if text_score is not None and lang.is_english:
                    parts.append(cmb.Part("Text", text_score, settings.weight_document_text))

        combined = cmb.combine(parts, settings, confirmed, confirmed_where, ai_hints)

    result = AnalysisResult(
        filename=vf.filename,
        sha256=vf.sha256,
        kind=vf.kind,
        size=vf.size,
        final_score=combined.score,
        label=combined.label,
        reason="",
        explanation=combined.explanation,
        signals=signals,
        warnings=warnings,
        chunks=chunks,
        language=language,
        provenance=prov.to_dict(),
        metadata=meta,
        av_status=vf.av_status,
        duration_s=round(time.monotonic() - started, 2),
    )
    result.reason = _reason(result)
    result.warnings += _disagreements(signals)
    return result


DISAGREE_GAP = 60  # percentage points between two detectors on the same input


def _disagreements(signals: list[Signal]) -> list[str]:
    """Warn when detectors looking at the same thing strongly disagree."""
    by_target: dict[tuple[str, str], list[Signal]] = {}
    for sig in signals:
        if sig.score is not None and sig.source in ("image_model", "text_model"):
            by_target.setdefault((sig.source, sig.target), []).append(sig)
    out = []
    for (_, target), sigs in by_target.items():
        hi, lo = max(sigs, key=lambda x: x.score), min(sigs, key=lambda x: x.score)
        if hi.score - lo.score >= DISAGREE_GAP:
            out.append(
                f"Detectors strongly disagree on {target} ({hi.name} {hi.score:.0f}% vs "
                f"{lo.name} {lo.score:.0f}%). Treat this result with extra caution."
            )
    return out
