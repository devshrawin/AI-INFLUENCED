"""Deletes stored uploads older than RETENTION_HOURS.

Runs in a background thread inside the app (every 15 minutes) and can also
be run by hand / cron:  python -m app.services.retention
Only uploaded files are deleted; the audit log rows (hash, scores) remain.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from sqlalchemy import update

from app.config import Settings, get_settings
from app.db.models import AuditLog
from app.db.session import new_session

log = logging.getLogger(__name__)

INTERVAL_SECONDS = 15 * 60


def purge_old_uploads(settings: Settings, now: float | None = None) -> int:
    now = now or time.time()
    cutoff = now - settings.retention_hours * 3600
    root = Path(settings.upload_dir)
    deleted: list[str] = []
    if root.exists():
        for path in root.rglob("*"):
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                deleted.append(str(path))
        for folder in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
            if not any(folder.iterdir()):
                folder.rmdir()
    if deleted:
        with new_session() as db:
            db.execute(update(AuditLog).where(AuditLog.stored_path.in_(deleted)).values(stored_path=None))
            db.commit()
        log.info("Retention: deleted %d upload(s) older than %d h", len(deleted), settings.retention_hours)
    return len(deleted)


class RetentionWorker(threading.Thread):
    def __init__(self, settings: Settings):
        super().__init__(name="retention", daemon=True)
        self.settings = settings
        self.stop_event = threading.Event()

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                purge_old_uploads(self.settings)
            except Exception:
                log.exception("Retention run failed")
            self.stop_event.wait(INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"Deleted {purge_old_uploads(get_settings())} file(s).")
