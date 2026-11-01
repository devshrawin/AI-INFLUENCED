"""Step 5: combine all signals into one explainable score.

The rule, in plain words:

1. A valid C2PA content credential that declares generative AI wins outright:
   score 99, label "AI (provenance-confirmed)".
2. Otherwise, each *part* of the file gets a score:
     - image part  = weighted average of the image models
     - text part   = weighted average of the text models, averaged over text
                     chunks (longer chunks count more). Ignored if the text is
                     not English or too short.
3. The final score is the weighted average of the parts
   (documents: text 70% / images 30% by default; only parts that exist count).
4. Unsigned metadata that names an AI tool adds a fixed bonus (default +15).
5. The label comes from the configurable thresholds.

Every number used is kept in the result so the screen can show exactly how
the final score was reached.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings

LABEL_PROVENANCE = "AI (provenance-confirmed)"
LABEL_AI = "Likely AI"
LABEL_UNSURE = "Not sure"
LABEL_HUMAN = "Likely Human"
LABEL_UNKNOWN = "Cannot assess"


@dataclass
class Part:
    """One scored part of the file (the text, or one image)."""

    name: str  # "Text", "Image", "Embedded image 2"
    score: float  # 0-100
    weight: float  # share in the final score (before normalising)


def weighted_mean(pairs: list[tuple[float, float]]) -> float | None:
    """Average of (value, weight) pairs; None if there is nothing to average."""
    total = sum(w for _, w in pairs if w > 0)
    if total <= 0:
        return None
    return sum(v * w for v, w in pairs if w > 0) / total


def label_for(score: float | None, settings: Settings) -> str:
    if score is None:
        return LABEL_UNKNOWN
    if score >= settings.threshold_ai:
        return LABEL_AI
    if score < settings.threshold_human:
        return LABEL_HUMAN
    return LABEL_UNSURE


@dataclass
class Combined:
    score: float | None
    label: str
    parts: list[Part]
    bonus: float
    explanation: list[str]


def combine(
    parts: list[Part],
    settings: Settings,
    provenance_confirmed: bool = False,
    provenance_where: str = "file",
    ai_hints: list[str] | None = None,
) -> Combined:
    explanation: list[str] = []
    if provenance_confirmed:
        explanation.append(
            f"Signed C2PA content credential in the {provenance_where} declares AI generation."
        )
        return Combined(99.0, LABEL_PROVENANCE, parts, 0.0, explanation)

    base = weighted_mean([(p.score, p.weight) for p in parts])
    total_w = sum(p.weight for p in parts if p.weight > 0)
    for p in parts:
        if p.weight > 0:
            explanation.append(f"{p.name}: {p.score:.0f}% (counts {p.weight / total_w:.0%})")

    bonus = 0.0
    if ai_hints:
        bonus = settings.metadata_hint_bonus
        explanation.append(f"Metadata names an AI tool (+{bonus:.0f}): {ai_hints[0]}")
        if base is None:
            # Only metadata: not enough for a confident label.
            explanation.append("No detector could score the content; metadata alone is weak evidence.")
            return Combined(None, LABEL_UNKNOWN, parts, bonus, explanation)

    if base is None:
        return Combined(
            None, LABEL_UNKNOWN, parts, 0.0, explanation or ["No detector could score this file."]
        )
    score = round(min(100.0, base + bonus), 1)
    return Combined(score, label_for(score, settings), parts, bonus, explanation)
