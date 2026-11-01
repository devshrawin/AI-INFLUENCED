"""Find earlier uploads of the same file or the same photo by OTHER applicants.

* exact file match: identical SHA-256 (any file type)
* photo match: perceptual-hash distance <= threshold (photos only, see fingerprint.py)

Uploads by the same applicant are ignored (re-submitting your own photo is normal).

Scale note: every check compares against all stored photo fingerprints in
one pass. That is a few hundred milliseconds for a million photos. Far beyond
that, add an index such as a BK-tree.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Fingerprint
from app.pipeline import fingerprint as fp

MAX_LISTED = 20  # matching applications listed in a flag


@dataclass
class Match:
    application_id: str
    applicant_id: str
    scheme: str
    file_name: str
    uploaded_at: str
    distance: int  # 0 for exact file matches

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _match(row: Fingerprint, dist: int) -> Match:
    return Match(row.application_id, row.applicant_id, row.scheme, row.file_name,
                 row.created_at.strftime("%Y-%m-%d %H:%M"), dist)  # fmt: skip


def _one_per_application(matches: list[Match]) -> list[Match]:
    seen, out = set(), []
    for m in sorted(matches, key=lambda m: (m.distance, m.uploaded_at)):
        if m.application_id not in seen:
            seen.add(m.application_id)
            out.append(m)
    return out


def exact_matches(db: Session, sha256: str, applicant_id: str) -> list[Match]:
    rows = db.scalars(
        select(Fingerprint).where(Fingerprint.sha256 == sha256, Fingerprint.applicant_id != applicant_id)
    ).all()
    return _one_per_application([_match(r, 0) for r in rows])


def photo_matches(
    db: Session, phash: int, applicant_id: str, max_distance: int, skip_sha: str
) -> list[Match]:
    rows = db.execute(
        select(Fingerprint.id, Fingerprint.phash).where(
            Fingerprint.kind == "photo",
            Fingerprint.phash.is_not(None),
            Fingerprint.applicant_id != applicant_id,
            Fingerprint.sha256 != skip_sha,  # exact copies are reported separately
        )
    ).all()
    close = {rid: d for rid, h in rows if (d := fp.distance(phash, fp.from_hex(h))) <= max_distance}
    if not close:
        return []
    found = db.scalars(select(Fingerprint).where(Fingerprint.id.in_(close))).all()
    return _one_per_application([_match(r, close[r.id]) for r in found])


def register(db: Session, **fields) -> None:
    """Store the fingerprint unless this application already has this exact file."""
    exists = db.scalar(
        select(Fingerprint.id).where(
            Fingerprint.application_id == fields["application_id"],
            Fingerprint.sha256 == fields["sha256"],
            Fingerprint.part == fields.get("part", "file"),
        )
    )
    if not exists:
        db.add(Fingerprint(**fields))
        db.commit()
