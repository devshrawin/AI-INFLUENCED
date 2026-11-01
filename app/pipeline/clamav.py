"""Minimal ClamAV (clamd) client using the documented INSTREAM protocol.

Written in-house (about 30 lines) instead of adding a third-party package.
Talks to clamd over its local UNIX socket only.
"""

from __future__ import annotations

import socket
import struct

CHUNK = 64 * 1024


def scan_bytes(data: bytes, socket_path: str, timeout: float = 60.0) -> tuple[str, str | None]:
    """Return ("OK", None) or ("FOUND", signature). Raises OSError if clamd is unreachable."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(socket_path)
        s.sendall(b"zINSTREAM\0")
        for i in range(0, len(data), CHUNK):
            chunk = data[i : i + CHUNK]
            s.sendall(struct.pack("!L", len(chunk)) + chunk)
        s.sendall(struct.pack("!L", 0))
        reply = b""
        while not reply.endswith(b"\0"):
            part = s.recv(4096)
            if not part:
                break
            reply += part
    text = reply.rstrip(b"\0").decode("utf-8", "replace")  # e.g. "stream: OK"
    body = text.split(":", 1)[-1].strip()
    if body.endswith("FOUND"):
        return "FOUND", body[: -len("FOUND")].strip()
    if body == "OK":
        return "OK", None
    return "ERROR", body
