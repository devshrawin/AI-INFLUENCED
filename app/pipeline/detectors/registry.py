"""Builds the detector objects once per process from settings."""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.pipeline.detectors.image import ImageClassifierDetector


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
