"""Builds the detector objects once per process from settings."""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.pipeline.detectors.image import ImageClassifierDetector
from app.pipeline.detectors.text import Binoculars, DesklibClassifier


@lru_cache
def image_detectors() -> list[tuple[ImageClassifierDetector, float]]:
    """[(detector, weight), ...] for images; empty if disabled."""
    s = get_settings()
    if not s.enable_image_detectors:
        return []
    return [
        (
            ImageClassifierDetector("Image model A (SwinV2)", s.models_dir, s.image_model_primary, s.device),
            s.weight_image_primary,
        ),
        (
            ImageClassifierDetector(
                "Image model B (SigLIP)", s.models_dir, s.image_model_secondary, s.device
            ),
            s.weight_image_secondary,
        ),
    ]


@lru_cache
def text_detectors() -> list[tuple[Binoculars | DesklibClassifier, float]]:
    """[(detector, weight), ...] for text; empty if all disabled."""
    s = get_settings()
    out: list = []
    if s.enable_binoculars:
        det = Binoculars(
            s.models_dir,
            s.binoculars_observer,
            s.binoculars_performer,
            s.device,
            threshold=s.binoculars_threshold,
            scale=s.binoculars_scale,
        )
        out.append((det, s.weight_text_binoculars))
    if s.enable_text_classifier:
        out.append(
            (DesklibClassifier(s.models_dir, s.text_model_classifier, s.device), s.weight_text_classifier)
        )
    return out
