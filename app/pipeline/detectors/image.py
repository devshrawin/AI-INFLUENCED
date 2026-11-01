"""Step 4a: local AI-image classifiers (Hugging Face image-classification models).

Both default models are binary classifiers whose labels say which class is
"AI" (e.g. "artificial"/"ai") and which is "real"/"hum". We read the label
names from the model config, so a different model can be dropped in via
settings without code changes, as long as one label looks like "AI".
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps

from app.pipeline.detectors.base import (
    DetectorOutput,
    LazyModel,
    ModelUnavailable,
    model_version,
    pick_device,
    require_model_dir,
)

AI_LABEL_WORDS = ("artificial", "ai", "fake", "generated", "synthetic")


def load_rgb(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)  # respect camera rotation
    return img.convert("RGB")


class ImageClassifierDetector(LazyModel):
    def __init__(self, name: str, models_dir: Path, folder: str, device_pref: str = "auto"):
        super().__init__()
        self.name = name
        self.models_dir = Path(models_dir)
        self.folder = folder
        self.device_pref = device_pref

    @property
    def model_id(self) -> str:
        return self.folder.replace("--", "/")

    @property
    def version(self) -> str:
        return model_version(self.models_dir, self.folder)

    def _load(self) -> None:
        import torch
        from transformers import AutoImageProcessor, AutoModelForImageClassification

        path = require_model_dir(self.models_dir, self.folder)
        self.device = pick_device(self.device_pref)
        self.processor = AutoImageProcessor.from_pretrained(path, local_files_only=True)
        self.model = AutoModelForImageClassification.from_pretrained(path, local_files_only=True)
        self.model.to(self.device).eval()
        labels = {int(k): v.lower() for k, v in self.model.config.id2label.items()}
        ai_ids = [i for i, lab in labels.items() if lab in AI_LABEL_WORDS or lab.startswith(AI_LABEL_WORDS)]
        if len(ai_ids) != 1:
            raise ModelUnavailable(f"Cannot tell which label means 'AI' in {labels}")
        self.ai_index = ai_ids[0]
        self._torch = torch

    def predict(self, data: bytes) -> DetectorOutput:
        self.ensure_loaded()
        img = load_rgb(data)
        inputs = self.processor(images=img, return_tensors="pt").to(self.device)
        with self._torch.inference_mode():
            logits = self.model(**inputs).logits[0]
        prob_ai = float(self._torch.softmax(logits.float(), dim=-1)[self.ai_index])
        return DetectorOutput(score=round(prob_ai * 100, 1), detail=f"{img.width}x{img.height} px")
