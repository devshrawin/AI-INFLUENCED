"""Offline guarantees: the tool must never reach the network."""

import re
import socket
from pathlib import Path

import pytest
from pytest_socket import SocketBlockedError

ROOT = Path(__file__).resolve().parent.parent


def test_outbound_network_is_blocked_in_tests():
    # pytest-socket is active for the whole test run (see pyproject.toml);
    # any code path that tries to connect out makes its test fail.
    with pytest.raises(SocketBlockedError):
        socket.create_connection(("example.com", 443), timeout=1)


def test_offline_env_flags_set():
    import os

    import app.offline  # noqa: F401

    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"


def test_no_external_urls_in_frontend():
    """Templates and static assets must not load anything from the internet."""
    pattern = re.compile(r"""(src|href)\s*=\s*["']?(https?:)?//""", re.I)
    for path in list((ROOT / "app" / "templates").rglob("*.html")) + [ROOT / "app" / "static" / "app.css"]:
        assert not pattern.search(path.read_text()), f"external URL in {path}"


def test_no_http_client_libraries_in_app():
    """App code must not import HTTP clients (requests, urllib.request, httpx...)."""
    banned = re.compile(r"^\s*(import|from)\s+(requests|httpx|urllib\.request|urllib3|aiohttp)\b", re.M)
    for path in (ROOT / "app").rglob("*.py"):
        assert not banned.search(path.read_text()), f"HTTP client imported in {path}"
