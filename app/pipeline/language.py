"""Language check before text scoring.

The text detectors are trained/calibrated mainly on English. For anything
else we show a warning and do not let the text score drive the label.

Method:
 1. Count letters per Unicode script. If most letters are in an Indian (or
    other non-Latin) script, the script names the language family directly
    (e.g. Malayalam script -> Malayalam). This covers languages that the
    `lingua` library does not support (Malayalam, Kannada, Odia...).
 2. For Latin-script text, `lingua` tells English from other Latin languages
    (Hinglish / transliterated text usually comes back as non-English or
    low-confidence, which is the safe outcome).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from functools import lru_cache

# Unicode script name prefix (from unicodedata.name) -> language label shown.
SCRIPT_LANG = {
    "MALAYALAM": "Malayalam",
    "DEVANAGARI": "Hindi/Marathi (Devanagari)",
    "TAMIL": "Tamil",
    "TELUGU": "Telugu",
    "KANNADA": "Kannada",
    "BENGALI": "Bengali/Assamese",
    "GUJARATI": "Gujarati",
    "GURMUKHI": "Punjabi",
    "ORIYA": "Odia",
    "ARABIC": "Urdu/Arabic",
    "CJK": "Chinese/Japanese",
    "HANGUL": "Korean",
    "CYRILLIC": "Cyrillic-script language",
    "THAI": "Thai",
    "GREEK": "Greek",
}


@dataclass
class LanguageResult:
    code: str  # "en" or a short code/name
    name: str
    confidence: float  # 0-1
    is_english: bool
    warning: str | None = None


def _script_of(ch: str) -> str:
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return "OTHER"
    if name.startswith("LATIN"):
        return "LATIN"
    for prefix in SCRIPT_LANG:
        if name.startswith(prefix):
            return prefix
    return "OTHER"


@lru_cache(maxsize=1)
def _lingua_detector():
    from lingua import Language, LanguageDetectorBuilder

    # Restricting to Latin-script languages keeps memory and time low.
    langs = [
        Language.ENGLISH, Language.FRENCH, Language.GERMAN, Language.SPANISH, Language.PORTUGUESE,
        Language.ITALIAN, Language.DUTCH, Language.INDONESIAN, Language.MALAY, Language.TAGALOG,
        Language.SWAHILI, Language.TURKISH, Language.VIETNAMESE, Language.POLISH, Language.LATIN,
    ]  # fmt: skip
    return LanguageDetectorBuilder.from_languages(*langs).with_preloaded_language_models().build()


def detect_language(text: str) -> LanguageResult:
    sample = text[:5000]
    counts: dict[str, int] = {}
    for ch in sample:
        if ch.isalpha():
            script = _script_of(ch)
            counts[script] = counts.get(script, 0) + 1
    total = sum(counts.values())
    if total == 0:
        return LanguageResult("und", "Unknown", 0.0, False, "No readable letters found.")

    top_script, top_count = max(counts.items(), key=lambda kv: kv[1])
    share = top_count / total
    if top_script != "LATIN":
        name = SCRIPT_LANG.get(top_script, "Non-Latin script")
        return LanguageResult(
            top_script.lower(), name, round(share, 2), False,
            f"Text appears to be {name}. The detectors are trained mainly on English, "
            "so the text score is NOT reliable and is not used for the label.",
        )  # fmt: skip

    detector = _lingua_detector()
    values = detector.compute_language_confidence_values(sample)
    best = values[0]
    is_en = best.language.name == "ENGLISH" and best.value >= 0.5
    mixed = share < 0.85  # e.g. English mixed with Malayalam script
    warning = None
    if not is_en:
        warning = (
            f"Text appears to be {best.language.name.title()} (or transliterated). Accuracy is low "
            "for non-English text; the text score is not used for the label."
        )
    elif mixed:
        warning = "Text mixes English with another script. Accuracy may be reduced."
    return LanguageResult(
        "en" if is_en else best.language.iso_code_639_1.name.lower(),
        best.language.name.title(),
        round(best.value, 2),
        is_en,
        warning,
    )
