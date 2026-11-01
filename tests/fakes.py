"""Fake detectors with fixed scores, so pipeline tests need no models."""

from app.pipeline.detectors.base import DetectorOutput, ModelUnavailable


class FakeDetector:
    def __init__(self, name, score, fail=False):
        self.name = name
        self.score = score
        self.fail = fail
        self.model_id = f"fake/{name}"
        self.version = "test"
        self.calls = 0

    def predict(self, payload):
        self.calls += 1
        if self.fail:
            raise ModelUnavailable("not installed")
        score = self.score(payload) if callable(self.score) else self.score
        return DetectorOutput(score=score, detail="fake")


def fake_image(a=80.0, b=60.0):
    return [(FakeDetector("imgA", a), 0.6), (FakeDetector("imgB", b), 0.4)]


def fake_text(a=90.0, b=70.0):
    return [(FakeDetector("bino", a), 0.5), (FakeDetector("clf", b), 0.5)]
