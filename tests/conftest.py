"""Shared test fixtures. Tests run with all network sockets disabled."""

import os
from pathlib import Path

import pytest

# Isolated settings for tests (set before the app is imported).
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("CLAMAV_ENABLED", "false")

SAMPLES = Path(__file__).parent / "samples"


@pytest.fixture
def sample():
    def _read(name: str) -> bytes:
        return (SAMPLES / name).read_bytes()

    return _read
