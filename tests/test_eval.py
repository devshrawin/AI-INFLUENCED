"""Evaluation script: metric maths and an end-to-end run with fake detectors."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("evaluate", ROOT / "eval" / "evaluate.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


def test_metrics():
    # truth, predicted
    pairs = [(True, True)] * 8 + [(True, False)] * 2 + [(False, False)] * 9 + [(False, True)]
    m = ev.metrics(pairs)
    assert (m["tp"], m["fn"], m["tn"], m["fp"]) == (8, 2, 9, 1)
    assert m["accuracy"] == 0.85 and m["recall"] == 0.8 and m["precision"] == 0.889
    assert m["false_positive_rate"] == 0.1


def test_metrics_empty():
    assert ev.metrics([])["accuracy"] is None


def test_end_to_end(tmp_path, sample, monkeypatch):
    from app.pipeline.detectors import registry
    from tests.fakes import FakeDetector

    for sub in ("real", "ai"):
        (tmp_path / sub).mkdir()
    (tmp_path / "real" / "h.txt").write_bytes(sample("human.txt"))
    (tmp_path / "ai" / "a.txt").write_bytes(sample("ai.txt"))
    (tmp_path / "real" / "p.png").write_bytes(sample("sample.png"))
    (tmp_path / "ai" / "c.jpg").write_bytes(sample("c2pa_ai.jpg"))
    (tmp_path / "ai" / "junk.png").write_bytes(sample("fake.png"))  # rejected, skipped

    monkeypatch.setattr(registry, "image_detectors", lambda: [(FakeDetector("img", 10.0), 1.0)])
    text = FakeDetector("txt", lambda t: 95.0 if "Artificial" in t else 5.0)
    monkeypatch.setattr(registry, "text_detectors", lambda: [(text, 1.0)])
    rows = ev.evaluate(tmp_path, None)
    summary = ev.summarise(rows)
    assert summary["text"]["balanced_at_50"]["accuracy"] == 1.0
    assert summary["image"]["likely_ai_label"]["tp"] == 1  # C2PA-confirmed image
    report = ev.to_markdown(summary, tmp_path)
    assert "## Text" in report and "## Image" in report
    json.dumps(summary)
