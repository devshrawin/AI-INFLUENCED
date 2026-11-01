import pytest

from app.config import get_settings
from app.pipeline.detectors.base import ModelUnavailable
from app.pipeline.detectors.text import Binoculars, DesklibClassifier


def _tiny_causal_lm(path):
    """Tiny random GPT-2 + word-level tokenizer, built offline for tests."""
    from tokenizers import Tokenizer, models, pre_tokenizers
    from transformers import GPT2Config, GPT2LMHeadModel, PreTrainedTokenizerFast

    vocab = {w: i for i, w in enumerate(["[UNK]", "[PAD]", *"the a cat dog sat on mat .".split()])}
    tok = Tokenizer(models.WordLevel(vocab, unk_token="[UNK]"))
    tok.pre_tokenizer = pre_tokenizers.Whitespace()
    fast = PreTrainedTokenizerFast(tokenizer_object=tok, unk_token="[UNK]", pad_token="[PAD]")
    fast.save_pretrained(path)
    GPT2LMHeadModel(GPT2Config(vocab_size=len(vocab), n_embd=16, n_layer=1, n_head=2)).save_pretrained(path)


def test_binoculars_with_tiny_models(tmp_path):
    for name in ("org--obs", "org--perf"):
        _tiny_causal_lm(tmp_path / name)
    det = Binoculars(tmp_path, "org--obs", "org--perf", "cpu")
    out = det.predict("the cat sat on the mat . the dog sat on a mat .")
    assert 0 <= out.score <= 100 and "binoculars=" in out.detail
    assert det.model_id == "binoculars:org/obs+org/perf"


def test_binoculars_probability_mapping():
    det = Binoculars("models", "a", "b", threshold=0.9, scale=0.04)
    assert det.to_probability(0.9) == pytest.approx(50)
    assert det.to_probability(0.7) > 99  # low score -> AI
    assert det.to_probability(1.1) < 1  # high score -> human


def test_missing_text_models(tmp_path):
    with pytest.raises(ModelUnavailable):
        DesklibClassifier(tmp_path, "x--y", "cpu").predict("hello")
    with pytest.raises(ModelUnavailable):
        Binoculars(tmp_path, "x--y", "x--z", "cpu").predict("hello")


@pytest.mark.models
def test_real_text_models_separate_samples(sample):
    s = get_settings()
    for det in (
        DesklibClassifier(s.models_dir, s.text_model_classifier, "cpu"),
        Binoculars(s.models_dir, s.binoculars_observer, s.binoculars_performer, "cpu"),
    ):
        try:
            det.ensure_loaded()
        except ModelUnavailable:
            pytest.skip("real text models not downloaded")
        ai = det.predict(sample("ai.txt").decode()).score
        human = det.predict(sample("human.txt").decode()).score
        assert ai > human, det.name
