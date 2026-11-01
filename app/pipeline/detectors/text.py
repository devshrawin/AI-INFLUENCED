"""Step 4b: local AI-text detectors.

1. `DesklibClassifier` — a DeBERTa-v3-large model fine-tuned to classify
   human vs AI text (desklib/ai-text-detector-v1.01, MIT licence).
2. `Binoculars` — a zero-shot method (Hans et al., 2024, "Spotting LLMs With
   Binoculars"). Two related language models read the text:
       score = log-perplexity(text, performer)  /  cross-perplexity(observer, performer)
   Machine text is unusually predictable for a language model *relative to
   how predictable a language model expects text to be*, so a LOW score means
   AI. No training data is needed. We use the small Qwen2.5-1.5B base +
   instruct pair so it runs on CPU; thresholds are calibrated for that pair
   (see eval/calibrate_binoculars.py) and can be changed in settings.
"""

from __future__ import annotations

import math
from pathlib import Path

from app.pipeline.detectors.base import (
    DetectorOutput,
    LazyModel,
    model_version,
    pick_device,
    require_model_dir,
)


class DesklibClassifier(LazyModel):
    name = "Text classifier (DeBERTa)"
    max_tokens = 768

    def __init__(self, models_dir: Path, folder: str, device_pref: str = "auto"):
        super().__init__()
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
        from torch import nn
        from transformers import AutoConfig, AutoModel, AutoTokenizer, PreTrainedModel

        class DesklibAIDetectionModel(PreTrainedModel):
            """Architecture published on the model card: DeBERTa + mean pooling + linear head."""

            config_class = AutoConfig

            def __init__(self, config):
                super().__init__(config)
                self.model = AutoModel.from_config(config)
                self.classifier = nn.Linear(config.hidden_size, 1)
                self.post_init()

            def forward(self, input_ids, attention_mask):
                hidden = self.model(input_ids, attention_mask=attention_mask)[0]
                mask = attention_mask.unsqueeze(-1).float()
                pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
                return self.classifier(pooled)

        path = require_model_dir(self.models_dir, self.folder)
        self.device = pick_device(self.device_pref)
        self.tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
        self.model = DesklibAIDetectionModel.from_pretrained(path, local_files_only=True)
        self.model.to(self.device).eval()
        self._torch = torch

    def predict(self, text: str) -> DetectorOutput:
        self.ensure_loaded()
        enc = self.tokenizer(text, truncation=True, max_length=self.max_tokens, return_tensors="pt").to(
            self.device
        )
        with self._torch.inference_mode():
            logit = self.model(enc["input_ids"], enc["attention_mask"])[0, 0].float().item()
        prob = 1 / (1 + math.exp(-logit))
        return DetectorOutput(score=round(prob * 100, 1), detail=f"{enc['input_ids'].shape[1]} tokens")


class Binoculars(LazyModel):
    name = "Binoculars (zero-shot)"
    max_tokens = 512

    def __init__(
        self,
        models_dir: Path,
        observer_folder: str,
        performer_folder: str,
        device_pref: str = "auto",
        threshold: float = 0.90,
        scale: float = 0.06,
    ):
        """threshold: Binoculars score at which P(AI) = 50%.
        scale: how quickly P(AI) moves away from 50% around the threshold."""
        super().__init__()
        self.models_dir = Path(models_dir)
        self.observer_folder = observer_folder
        self.performer_folder = performer_folder
        self.device_pref = device_pref
        self.threshold = threshold
        self.scale = scale

    @property
    def model_id(self) -> str:
        return (
            f"binoculars:{self.observer_folder.replace('--', '/')}+{self.performer_folder.replace('--', '/')}"
        )

    @property
    def version(self) -> str:
        return (
            f"{model_version(self.models_dir, self.observer_folder)}+"
            f"{model_version(self.models_dir, self.performer_folder)}"
        )

    def _load(self) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        obs_path = require_model_dir(self.models_dir, self.observer_folder)
        perf_path = require_model_dir(self.models_dir, self.performer_folder)
        self.device = pick_device(self.device_pref)
        # bfloat16 halves memory (about 3 GB per model) on both CPU and GPU.
        dtype = torch.bfloat16
        self.tokenizer = AutoTokenizer.from_pretrained(obs_path, local_files_only=True)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.observer = AutoModelForCausalLM.from_pretrained(obs_path, dtype=dtype, local_files_only=True)
        self.performer = AutoModelForCausalLM.from_pretrained(perf_path, dtype=dtype, local_files_only=True)
        self.observer.to(self.device).eval()
        self.performer.to(self.device).eval()
        self._torch = torch

    def raw_score(self, text: str) -> tuple[float, int]:
        """Return (binoculars score, number of tokens)."""
        torch = self._torch
        enc = self.tokenizer(text, truncation=True, max_length=self.max_tokens, return_tensors="pt").to(
            self.device
        )
        ids = enc["input_ids"]
        with torch.inference_mode():
            obs_logits = self.observer(**enc).logits[0, :-1].float()
            perf_logits = self.performer(**enc).logits[0, :-1].float()
        targets = ids[0, 1:]
        # log-perplexity of the text under the performer model
        log_ppl = torch.nn.functional.cross_entropy(perf_logits, targets).item()
        # cross-perplexity: observer's expected loss under performer's predictions
        obs_probs = torch.softmax(obs_logits, dim=-1)
        perf_logp = torch.log_softmax(perf_logits, dim=-1)
        x_ppl = (-(obs_probs * perf_logp).sum(-1)).mean().item()
        return log_ppl / x_ppl, int(ids.shape[1])

    def to_probability(self, score: float) -> float:
        """Map the raw score to 0-100 (low Binoculars score -> high AI %)."""
        return 100 / (1 + math.exp((score - self.threshold) / self.scale))

    def predict(self, text: str) -> DetectorOutput:
        self.ensure_loaded()
        score, n_tokens = self.raw_score(text)
        return DetectorOutput(
            score=round(self.to_probability(score), 1),
            detail=f"binoculars={score:.3f} (AI if < {self.threshold:.3f}), {n_tokens} tokens",
        )
