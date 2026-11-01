#!/usr/bin/env python3
"""Measure how well the tool works on a labelled set of files.

Usage:
    python eval/evaluate.py <folder> [--out eval/reports] [--limit N]

<folder> must contain two sub-folders:
    real/   files made by people  (any supported type: pdf, docx, txt, jpg, png, webp)
    ai/     files made with AI

The full pipeline (validation, provenance, models, combining) is run on every
file, exactly as in the web tool. Separate reports are written for images and
for text documents:

  * accuracy, precision, recall, false-positive rate, F1 and a confusion
    matrix when "AI" means final score >= 50 (balanced decision)
  * the same when "AI" means the "Likely AI" label (score >= THRESHOLD_AI),
    which is how officers see it
  * how often the tool said "Not sure" / "Cannot assess"
  * per-detector accuracy, to help tune weights

Outputs report.md and results.json (+ results.csv) in --out.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app  # noqa: E402,F401  (forces offline mode)
from app.config import get_settings  # noqa: E402
from app.pipeline.combine import LABEL_AI, LABEL_HUMAN, LABEL_PROVENANCE  # noqa: E402
from app.pipeline.orchestrator import analyze  # noqa: E402
from app.pipeline.validate import ValidationError, validate_upload  # noqa: E402

AI_LABELS = {LABEL_AI, LABEL_PROVENANCE}


def metrics(pairs: list[tuple[bool, bool]]) -> dict:
    """pairs = [(truth_is_ai, predicted_ai), ...]"""
    tp = sum(t and p for t, p in pairs)
    tn = sum((not t) and (not p) for t, p in pairs)
    fp = sum((not t) and p for t, p in pairs)
    fn = sum(t and (not p) for t, p in pairs)
    n = len(pairs)

    def div(a, b):
        return round(a / b, 3) if b else None

    precision, recall = div(tp, tp + fp), div(tp, tp + fn)
    f1 = round(2 * precision * recall / (precision + recall), 3) if precision and recall else None
    return {
        "n": n, "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "accuracy": div(tp + tn, n), "precision": precision, "recall": recall,
        "false_positive_rate": div(fp, fp + tn), "f1": f1,
    }  # fmt: skip


def evaluate(root: Path, limit: int | None) -> list[dict]:
    settings = get_settings()
    rows = []
    files = [(lab, p) for lab in ("real", "ai") for p in sorted((root / lab).glob("*")) if p.is_file()]
    if limit:
        files = [f for lab in ("real", "ai") for f in [x for x in files if x[0] == lab][:limit]]
    for i, (truth, path) in enumerate(files, 1):
        started = time.monotonic()
        try:
            vf = validate_upload(path.read_bytes(), path.name, settings)
        except ValidationError as exc:
            print(f"[{i}/{len(files)}] skip {path.name}: {exc}")
            continue
        r = analyze(vf, settings)
        detectors = {
            s.name: s.score for s in r.signals if s.score is not None and s.source.endswith("_model")
        }
        rows.append({
            "file": f"{truth}/{path.name}", "truth": truth,
            "modality": "image" if vf.is_image else "text",
            "score": r.final_score, "label": r.label, "detectors": detectors,
            "seconds": round(time.monotonic() - started, 2),
        })  # fmt: skip
        print(f"[{i}/{len(files)}] {truth:4s} {r.label:26s} {r.final_score!s:>6}  {path.name}", flush=True)
    return rows


def summarise(rows: list[dict]) -> dict:
    settings = get_settings()
    out = {}
    for modality in ("image", "text"):
        subset = [r for r in rows if r["modality"] == modality]
        if not subset:
            continue
        scored = [r for r in subset if r["score"] is not None]
        labels = Counter((r["truth"], r["label"]) for r in subset)
        per_det: dict[str, list[tuple[bool, bool]]] = {}
        for r in subset:
            for name, score in r["detectors"].items():
                per_det.setdefault(name, []).append((r["truth"] == "ai", score >= 50))
        out[modality] = {
            "files": len(subset),
            "cannot_assess": len(subset) - len(scored),
            "balanced_at_50": metrics([(r["truth"] == "ai", r["score"] >= 50) for r in scored]),
            "likely_ai_label": metrics([(r["truth"] == "ai", r["label"] in AI_LABELS) for r in subset]),
            "not_sure_rate": round(sum(r["label"] == "Not sure" for r in subset) / len(subset), 3),
            "likely_human_but_ai": labels[("ai", LABEL_HUMAN)],
            "label_matrix": {f"{t} -> {lab}": c for (t, lab), c in sorted(labels.items())},
            "per_detector_at_50": {k: metrics(v) for k, v in per_det.items()},
            "avg_seconds": round(sum(r["seconds"] for r in subset) / len(subset), 2),
            "thresholds": {"ai": settings.threshold_ai, "human": settings.threshold_human},
        }
    return out


def confusion_md(m: dict) -> str:
    return (
        "|              | predicted AI | predicted human |\n|---|---|---|\n"
        f"| **truly AI**    | {m['tp']} | {m['fn']} |\n| **truly human** | {m['fp']} | {m['tn']} |\n"
    )


def to_markdown(summary: dict, root: Path) -> str:
    lines = [f"# Evaluation report\n\nDataset: `{root}`  \nRun: {datetime.now(UTC):%Y-%m-%d %H:%M} UTC\n"]
    for modality, s in summary.items():
        b, lab = s["balanced_at_50"], s["likely_ai_label"]
        lines += [
            f"## {modality.title()} ({s['files']} files)\n",
            "| Metric | Score >= 50 | 'Likely AI' label |", "|---|---|---|",
            *[f"| {k.replace('_', ' ')} | {b[k]} | {lab[k]} |"
              for k in ("accuracy", "precision", "recall", "false_positive_rate", "f1")],
            "", "**Confusion matrix (score >= 50):**\n", confusion_md(b),
            f"'Not sure' rate: {s['not_sure_rate']:.0%}  ·  Cannot assess: {s['cannot_assess']}  ·  "
            f"AI files labelled 'Likely Human': {s['likely_human_but_ai']}  ·  "
            f"avg {s['avg_seconds']} s/file\n",
            "**Labels given:**\n", *[f"- {k}: {v}" for k, v in s["label_matrix"].items()], "",
            "**Each detector alone (score >= 50):**\n", "| Detector | accuracy | precision | recall | FPR |",
            "|---|---|---|---|---|",
            *[f"| {name} | {m['accuracy']} | {m['precision']} | {m['recall']} | {m['false_positive_rate']} |"
              for name, m in s["per_detector_at_50"].items()], "",
        ]  # fmt: skip
    return "\n".join(lines)


def main() -> int:
    fmt = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=fmt)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--out", type=Path, default=Path("eval/reports"))
    parser.add_argument("--limit", type=int, help="max files per class (quick runs)")
    args = parser.parse_args()
    for sub in ("real", "ai"):
        if not (args.folder / sub).is_dir():
            parser.error(f"{args.folder / sub} not found")
    rows = evaluate(args.folder, args.limit)
    summary = summarise(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "results.json").write_text(json.dumps({"summary": summary, "files": rows}, indent=2))
    with (args.out / "results.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "truth", "modality", "score", "label", "seconds"])
        for r in rows:
            w.writerow([r["file"], r["truth"], r["modality"], r["score"], r["label"], r["seconds"]])
    report = to_markdown(summary, args.folder)
    (args.out / "report.md").write_text(report)
    print("\n" + report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
