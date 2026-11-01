"""Shared test fixtures. Tests run with all network sockets disabled."""

import os
import re
from pathlib import Path

import pytest

# Isolated settings for tests (set before the app is imported).
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["CLAMAV_ENABLED"] = "false"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = ""
os.environ.setdefault("UPLOAD_DIR", str(Path(__file__).parent / ".tmp_uploads"))

SAMPLES = Path(__file__).parent / "samples"
PASSWORD = "Test-pass-123"


@pytest.fixture
def sample():
    def _read(name: str) -> bytes:
        return (SAMPLES / name).read_bytes()

    return _read


@pytest.fixture
def db():
    """Fresh empty database for each test."""
    from app.db.models import Base
    from app.db.session import get_engine, new_session

    Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())
    with new_session() as session:
        yield session


@pytest.fixture
def make_user(db):
    from app.auth.passwords import hash_password
    from app.db.models import User

    def _make(username="officer1", role="officer", must_change=False, password=PASSWORD):
        user = User(username=username, role=role, password_hash=hash_password(password),
                    must_change_password=must_change)  # fmt: skip
        db.add(user)
        db.commit()
        return user

    return _make


@pytest.fixture
def client(db, monkeypatch):
    """Test client with fake detectors and rate limiting off."""
    from fastapi.testclient import TestClient

    from app.api.limiter import limiter
    from app.main import create_app
    from app.pipeline.detectors import registry
    from tests.fakes import fake_image, fake_text

    monkeypatch.setattr(registry, "image_detectors", lambda: fake_image(90, 90))
    monkeypatch.setattr(registry, "text_detectors", lambda: fake_text(10, 10))
    limiter.enabled = False
    limiter.reset()
    with TestClient(create_app(start_background=False)) as c:
        yield c
    limiter.enabled = True


def csrf_of(html: str) -> str:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html) or re.search(r'"X-CSRF-Token": "([^"]+)"', html)
    assert m, "no CSRF token in page"
    return m.group(1)


def login(client, username="officer1", password=PASSWORD):
    token = csrf_of(client.get("/login").text)
    return client.post("/login", data={"username": username, "password": password, "csrf_token": token},
                       follow_redirects=False)  # fmt: skip
