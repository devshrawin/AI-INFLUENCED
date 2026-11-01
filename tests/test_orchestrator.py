from app.config import Settings
from app.pipeline.combine import LABEL_AI, LABEL_PROVENANCE, LABEL_UNKNOWN
from app.pipeline.orchestrator import analyze
from app.pipeline.validate import validate_upload
from tests.fakes import FakeDetector, fake_image, fake_text

S = Settings(clamav_enabled=False, min_words_for_text_score=20)


def _vf(sample, name):
    return validate_upload(sample(name), name, S)


def test_image_path(sample):
    r = analyze(_vf(sample, "sample.png"), S, image_dets=fake_image(80, 60), text_dets=fake_text())
    assert r.final_score == 72.0  # 0.6*80 + 0.4*60
    assert r.label == LABEL_AI
    assert {s.name for s in r.signals if s.source == "image_model"} == {"imgA", "imgB"}
    assert r.model_versions() == {"fake/imgA": "test", "fake/imgB": "test"}
    assert "not proof" in r.disclaimer


def test_c2pa_image_confirmed(sample):
    r = analyze(_vf(sample, "c2pa_ai.jpg"), S, image_dets=fake_image(1, 1), text_dets=[])
    assert r.label == LABEL_PROVENANCE and r.final_score == 99


def test_txt_english(sample):
    r = analyze(_vf(sample, "ai.txt"), S, image_dets=fake_image(), text_dets=fake_text(90, 70))
    assert r.final_score == 80.0
    assert r.language["is_english"]
    assert len(r.chunks) == 1


def test_txt_non_english_not_used_for_label(sample):
    r = analyze(_vf(sample, "malayalam.txt"), Settings(clamav_enabled=False, min_words_for_text_score=5),
                image_dets=[], text_dets=fake_text(99, 99))  # fmt: skip
    assert r.label == LABEL_UNKNOWN and r.final_score is None
    assert any("Malayalam" in w for w in r.warnings)
    assert all(s.weight == 0 for s in r.signals if s.source == "text_model")


def test_docx_text_and_images(sample):
    r = analyze(_vf(sample, "sample.docx"), S, image_dets=fake_image(20, 20), text_dets=fake_text(90, 90))
    # text 90 * 0.7 + image 20 * 0.3 = 69
    assert r.final_score == 69.0
    assert any(s.target == "embedded image 1" for s in r.signals)


def test_pdf(sample):
    r = analyze(_vf(sample, "sample.pdf"), S, image_dets=fake_image(50, 50), text_dets=fake_text(50, 50))
    assert r.final_score == 50.0


def test_long_text_chunks_ranked(sample):
    text = ("Human sentence here about the market and the rain. " * 60 + "\n") + (
        "Furthermore, leveraging synergies enhances outcomes. " * 60
    )
    vf = validate_upload(text.encode(), "long.txt", S)

    def score(t):
        return 95.0 if "leveraging" in t else 5.0

    dets = [(FakeDetector("bino", score), 1.0)]
    r = analyze(vf, Settings(clamav_enabled=False, chunk_tokens=200), image_dets=[], text_dets=dets)
    assert len(r.chunks) > 2
    assert r.top_chunks[0].score == 95.0 and "leveraging" in r.top_chunks[0].excerpt


def test_missing_models_degrade_gracefully(sample):
    broken = [(FakeDetector("imgA", 0, fail=True), 1.0)]
    r = analyze(_vf(sample, "sample.png"), S, image_dets=broken, text_dets=[])
    assert r.label == LABEL_UNKNOWN
    assert any("unavailable" in w for w in r.warnings)


def test_short_text_warning(sample):
    vf = validate_upload(b"Just a few words here.", "short.txt", S)
    r = analyze(vf, S, image_dets=[], text_dets=fake_text())
    assert r.final_score is None and any("words" in w for w in r.warnings)


def test_result_serialisable(sample):
    import json

    r = analyze(_vf(sample, "sample.docx"), S, image_dets=fake_image(), text_dets=fake_text())
    json.dumps(r.to_dict(), default=str)


def test_disagreement_warning(sample):
    r = analyze(_vf(sample, "sample.png"), S, image_dets=fake_image(95, 5), text_dets=[])
    assert any("strongly disagree" in w for w in r.warnings)
    r = analyze(_vf(sample, "sample.png"), S, image_dets=fake_image(60, 50), text_dets=[])
    assert not any("strongly disagree" in w for w in r.warnings)


def test_tiny_image_not_scored():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (10, 200, 30)).save(buf, "PNG")
    vf = validate_upload(buf.getvalue(), "tiny.png", S)
    dets = fake_image(99, 99)
    r = analyze(vf, S, image_dets=dets, text_dets=[])
    assert r.label == LABEL_UNKNOWN and any("32x32" in w for w in r.warnings)
    assert dets[0][0].calls == 0
