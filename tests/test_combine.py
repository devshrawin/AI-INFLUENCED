import pytest

from app.config import Settings
from app.pipeline.combine import (
    LABEL_AI,
    LABEL_HUMAN,
    LABEL_PROVENANCE,
    LABEL_UNKNOWN,
    LABEL_UNSURE,
    Part,
    combine,
    label_for,
)  # fmt: skip

S = Settings()


CASES = [(95, LABEL_AI), (70, LABEL_AI), (69.9, LABEL_UNSURE), (30, LABEL_UNSURE), (29.9, LABEL_HUMAN)]


@pytest.mark.parametrize("score,label", [*CASES, (None, LABEL_UNKNOWN)])
def test_labels(score, label):
    assert label_for(score, S) == label


def test_thresholds_configurable():
    s = Settings(threshold_ai=90, threshold_human=10)
    assert label_for(80, s) == LABEL_UNSURE


def test_weighted_parts():
    c = combine([Part("Text", 80, 0.7), Part("Images", 20, 0.3)], S)
    assert c.score == pytest.approx(62.0)
    assert c.label == LABEL_UNSURE
    assert any("Text: 80%" in e for e in c.explanation)


def test_provenance_overrides():
    c = combine([Part("Image", 5, 1)], S, provenance_confirmed=True)
    assert c.score == 99 and c.label == LABEL_PROVENANCE


def test_metadata_bonus_capped():
    c = combine([Part("Image", 95, 1)], S, ai_hints=["EXIF Software mentions 'midjourney'"])
    assert c.score == 100 and c.bonus == S.metadata_hint_bonus


def test_metadata_alone_is_not_enough():
    c = combine([], S, ai_hints=["x"])
    assert c.score is None and c.label == LABEL_UNKNOWN


def test_nothing_scored():
    assert combine([], S).label == LABEL_UNKNOWN
