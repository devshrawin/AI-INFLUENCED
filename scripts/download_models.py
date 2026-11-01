#!/usr/bin/env python3
"""Download all detector models (run on an INTERNET-connected machine).

Usage:
    python scripts/download_models.py [--dest models] [--only image|text|all]
                                      [--skip-binoculars]

Writes each model to  <dest>/<owner>--<name>/  and a manifest
<dest>/MANIFEST.json  with the exact revision (commit hash), licence and a
SHA-256 checksum of every file. The manifest is checked inside the SDC by
scripts/verify_bundle.py and shown in the audit log.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# repo id -> (group, licence). Only permissively licensed models are listed.
MODELS = {
    "haywoodsloan/ai-image-detector-deploy": ("image", "apache-2.0"),
    "Ateeqq/ai-vs-human-image-detector": ("image", "apache-2.0"),
    "desklib/ai-text-detector-v1.01": ("text", "mit"),
    "Qwen/Qwen2.5-1.5B": ("binoculars", "apache-2.0"),
    "Qwen/Qwen2.5-1.5B-Instruct": ("binoculars", "apache-2.0"),
}

# Only weights/config/tokenizer files; skip duplicate formats (.bin, onnx...).
ALLOW_PATTERNS = [
    "*.json",
    "*.safetensors",
    "*.txt",
    "*.model",
    "tokenizer*",
    "*.py",
    "README.md",
    "LICENSE*",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def folder_name(repo_id: str) -> str:
    return repo_id.replace("/", "--")


def main() -> int:
    fmt = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=fmt)
    parser.add_argument("--dest", default="models")
    parser.add_argument("--only", choices=["image", "text", "all"], default="all")
    parser.add_argument("--skip-binoculars", action="store_true", help="skip the 2 x 3 GB Qwen models")
    args = parser.parse_args()

    from huggingface_hub import HfApi, snapshot_download

    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    manifest_path = dest / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"models": {}}
    api = HfApi()

    for repo_id, (group, licence) in MODELS.items():
        if args.only == "image" and group != "image":
            continue
        if args.only == "text" and group == "image":
            continue
        if args.skip_binoculars and group == "binoculars":
            continue
        info = api.model_info(repo_id)
        target = dest / folder_name(repo_id)
        print(f"-> {repo_id} @ {info.sha[:10]}  ->  {target}")
        snapshot_download(repo_id, revision=info.sha, local_dir=target, allow_patterns=ALLOW_PATTERNS)
        files = {
            str(p.relative_to(target)): sha256_file(p)
            for p in sorted(target.rglob("*"))
            if p.is_file() and ".cache" not in p.parts
        }
        manifest["models"][folder_name(repo_id)] = {
            "repo_id": repo_id,
            "revision": info.sha,
            "licence": licence,
            "group": group,
            "downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "files": files,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2))

    print(f"Manifest written to {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
