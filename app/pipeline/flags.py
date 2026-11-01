"""Flags shown to officers, and the overall level for a file.

Levels:
  high    - strong evidence (signed AI credential, same photo/file as another applicant)
  review  - worth a look (unsigned AI hint in metadata, broken credential, very similar photo)
  info    - noted, not a reason to review on its own (e.g. edited in Photoshop)
The overall level of a file is the highest level of its flags ("none" if no
high/review flags).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

HIGH, REVIEW, INFO, NONE = "high", "review", "info", "none"
_ORDER = {NONE: 0, INFO: 0, REVIEW: 1, HIGH: 2}
DISCLAIMER = "This is an indicator for human review, not proof."

HEADLINES = {
    HIGH: "Flagged: please review before approving.",
    REVIEW: "Worth a closer look.",
    NONE: "No issues found.",
}


@dataclass
class Flag:
    code: str  # machine-readable, e.g. DUPLICATE_PHOTO
    level: str  # high | review | info
    message: str  # plain sentence for the officer
    target: str = "file"  # "file" or "embedded image 2"
    matches: list[dict[str, Any]] = field(default_factory=list)  # for duplicates

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def overall_level(flags: list[Flag]) -> str:
    best = NONE
    for f in flags:
        if _ORDER[f.level] > _ORDER[best]:
            best = f.level
    return best


def build_note(flags: list[Flag]) -> str:
    """Short plain-text note to attach to the application."""
    level = overall_level(flags)
    lines = [HEADLINES[level]]
    for f in sorted(flags, key=lambda f: -_ORDER[f.level]):
        if f.level != INFO:
            where = "" if f.target == "file" else f" ({f.target})"
            lines.append(f"- {f.message}{where}")
    if level != NONE:
        lines.append(DISCLAIMER)
    return "\n".join(lines)
