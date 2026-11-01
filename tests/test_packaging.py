"""Offline packaging helpers: checksum verification."""

import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("verify_bundle", ROOT / "scripts" / "verify_bundle.py")
vb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vb)


def _make_bundle(root: Path):
    (root / "models" / "org--m").mkdir(parents=True)
    weights = root / "models" / "org--m" / "model.safetensors"
    weights.write_bytes(b"weights")
    digest = hashlib.sha256(b"weights").hexdigest()
    manifest = {"models": {"org--m": {"repo_id": "org/m", "revision": "abc123def456", "licence": "mit",
                                      "files": {"model.safetensors": digest}}}}  # fmt: skip
    (root / "models" / "MANIFEST.json").write_text(json.dumps(manifest))
    (root / "images.tar").write_bytes(b"images")
    lines = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  ./{p.relative_to(root)}")
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n")
    return weights


def test_good_bundle_passes(tmp_path):
    _make_bundle(tmp_path)
    assert vb.main([str(tmp_path)]) == 0


def test_tampered_model_fails(tmp_path):
    weights = _make_bundle(tmp_path)
    weights.write_bytes(b"evil")
    assert vb.main([str(tmp_path)]) == 1
    assert vb.main(["--models-only", str(tmp_path / "models")]) == 1


def test_missing_file_fails(tmp_path):
    _make_bundle(tmp_path)
    (tmp_path / "images.tar").unlink()
    assert vb.main([str(tmp_path)]) == 1


def test_bundle_without_models_folder(tmp_path):
    (tmp_path / "images.tar").write_bytes(b"images")
    digest = hashlib.sha256(b"images").hexdigest()
    (tmp_path / "SHA256SUMS").write_text(f"{digest}  ./images.tar\n")
    assert vb.main([str(tmp_path)]) == 0
