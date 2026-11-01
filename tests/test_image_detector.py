import pytest

from app.config import get_settings
from app.pipeline.detectors.base import ModelUnavailable
from app.pipeline.detectors.image import ImageClassifierDetector


def _tiny_vit(path, id2label):
    """Save a tiny random ViT classifier so tests need no real weights."""
    from transformers import ViTConfig, ViTForImageClassification, ViTImageProcessor

    cfg = ViTConfig(
        image_size=32, patch_size=16, hidden_size=16, num_hidden_layers=1, num_attention_heads=2,
        intermediate_size=32, id2label=id2label, label2id={v: k for k, v in id2label.items()},
    )  # fmt: skip
    ViTForImageClassification(cfg).save_pretrained(path)
    ViTImageProcessor(size={"height": 32, "width": 32}).save_pretrained(path)


def test_tiny_model_scores_between_0_and_100(tmp_path, sample):
    _tiny_vit(tmp_path / "org--tiny", {0: "real", 1: "fake"})
    det = ImageClassifierDetector("tiny", tmp_path, "org--tiny", "cpu")
    out = det.predict(sample("sample.png"))
    assert 0 <= out.score <= 100
    assert det.ai_index == 1
    assert det.model_id == "org/tiny"


def test_unclear_labels_rejected(tmp_path, sample):
    _tiny_vit(tmp_path / "org--bad", {0: "cat", 1: "dog"})
    det = ImageClassifierDetector("bad", tmp_path, "org--bad", "cpu")
    with pytest.raises(ModelUnavailable):
        det.predict(sample("sample.png"))


def test_missing_model_folder(tmp_path, sample):
    det = ImageClassifierDetector("missing", tmp_path, "nope--nope", "cpu")
    with pytest.raises(ModelUnavailable, match="download_models"):
        det.predict(sample("sample.png"))
    with pytest.raises(ModelUnavailable):  # error is remembered, no retry storm
        det.predict(sample("sample.png"))


@pytest.mark.models
@pytest.mark.parametrize("folder", ["image_model_primary", "image_model_secondary"])
def test_real_image_models(folder, sample):
    s = get_settings()
    det = ImageClassifierDetector("real", s.models_dir, getattr(s, folder), "cpu")
    try:
        det.ensure_loaded()
    except ModelUnavailable:
        pytest.skip("real model not downloaded")
    for name in ("sample.jpg", "sample.png", "sample.webp"):
        assert 0 <= det.predict(sample(name)).score <= 100
