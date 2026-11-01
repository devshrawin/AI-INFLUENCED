#!/usr/bin/env python3
"""Verify an unpacked offline bundle inside the SDC before installing.

Usage:
    python3 scripts/verify_bundle.py <unpacked bundle folder>
    python3 scripts/verify_bundle.py --models-only <models folder>

Checks:
  1. every file listed in SHA256SUMS exists and matches
  2. if the bundle has a models/ folder (older versions), every file in
     models/MANIFEST.json exists and matches
Exit code 0 = all good, 1 = problem found. Uses only the Python standard library.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def check_sums(root: Path) -> list[str]:
    problems = []
    sums = root / "SHA256SUMS"
    if not sums.exists():
        return [f"{sums} not found"]
    lines = [ln for ln in sums.read_text().splitlines() if ln.strip()]
    for i, line in enumerate(lines, 1):
        expected, name = line.split(maxsplit=1)
        path = root / name.lstrip("*").removeprefix("./")
        if not path.exists():
            problems.append(f"MISSING  {name}")
        elif sha256(path) != expected:
            problems.append(f"CHANGED  {name}")
        print(f"\r  checked {i}/{len(lines)} files", end="", flush=True)
    print()
    return problems


def check_models(models: Path) -> list[str]:
    manifest = models / "MANIFEST.json"
    if not manifest.exists():
        return [f"{manifest} not found"]
    problems = []
    for folder, entry in json.loads(manifest.read_text())["models"].items():
        print(f"  {entry['repo_id']} @ {entry['revision'][:10]} ({entry['licence']})")
        for rel, expected in entry["files"].items():
            path = models / folder / rel
            if not path.exists():
                problems.append(f"MISSING  {folder}/{rel}")
            elif sha256(path) != expected:
                problems.append(f"CHANGED  {folder}/{rel}")
    return problems


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    if argv[0] == "--models-only":
        problems = check_models(Path(argv[1]))
    else:
        root = Path(argv[0])
        print("Checking bundle checksums (SHA256SUMS)...")
        problems = check_sums(root)
        if (root / "models").is_dir():
            print("Checking model checksums (models/MANIFEST.json)...")
            problems += check_models(root / "models")
    if problems:
        print("\nVERIFICATION FAILED:")
        for p in problems:
            print("  " + p)
        print("Do NOT install. Copy the bundle again from the source machine.")
        return 1
    print("\nAll checksums match. The bundle is safe to install.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
