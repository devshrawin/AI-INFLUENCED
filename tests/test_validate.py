import pytest

from app.config import Settings
from app.pipeline.validate import ValidationError, validate_upload


@pytest.fixture
def settings():
    return Settings(clamav_enabled=False, max_upload_mb=1)


@pytest.mark.parametrize(
    "name,kind",
    [
        ("sample.png", "png"),
        ("sample.jpg", "jpeg"),
        ("sample.webp", "webp"),
        ("sample.pdf", "pdf"),
        ("sample.docx", "docx"),
        ("human.txt", "txt"),
        ("malayalam.txt", "txt"),
    ],
)
def test_accepts_supported_types(sample, settings, name, kind):
    vf = validate_upload(sample(name), name, settings)
    assert vf.kind == kind
    assert len(vf.sha256) == 64


def test_type_from_magic_bytes_not_extension(sample, settings):
    # A real PNG named .pdf is still detected as PNG.
    assert validate_upload(sample("sample.png"), "x.pdf", settings).kind == "png"


def test_rejects_executable_disguised_as_png(sample, settings):
    with pytest.raises(ValidationError, match="Unsupported"):
        validate_upload(sample("fake.png"), "fake.png", settings)


def test_rejects_empty(settings):
    with pytest.raises(ValidationError, match="empty"):
        validate_upload(b"", "a.txt", settings)


def test_rejects_oversize(settings):
    with pytest.raises(ValidationError, match="limit"):
        validate_upload(b"a" * (settings.max_upload_bytes + 1), "a.txt", settings)


def test_rejects_plain_zip(settings):
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("hello.txt", "hi")
    with pytest.raises(ValidationError):
        validate_upload(buf.getvalue(), "a.docx", settings)


def test_clamav_unavailable_not_required(sample):
    s = Settings(clamav_enabled=True, clamav_socket="/nonexistent.sock", clamav_required=False)
    assert validate_upload(sample("human.txt"), "a.txt", s).av_status == "unavailable"


def test_clamav_unavailable_required_rejects(sample):
    s = Settings(clamav_enabled=True, clamav_socket="/nonexistent.sock", clamav_required=True)
    with pytest.raises(ValidationError, match="unavailable"):
        validate_upload(sample("human.txt"), "a.txt", s)


def test_clamav_infected(monkeypatch, sample):
    from app.pipeline import clamav

    monkeypatch.setattr(clamav, "scan_bytes", lambda data, path: ("FOUND", "Eicar-Test-Signature"))
    with pytest.raises(ValidationError, match="Eicar"):
        validate_upload(sample("human.txt"), "a.txt", Settings(clamav_enabled=True))


def test_clamav_protocol_against_fake_daemon(tmp_path):
    """Run our INSTREAM client against a tiny fake clamd on a UNIX socket."""
    import socket
    import threading

    from app.pipeline import clamav

    path = str(tmp_path / "clamd.sock")
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    srv.listen(1)

    def serve():
        conn, _ = srv.accept()
        buf = b""
        while not buf.endswith(b"\0\0\0\0"):
            buf += conn.recv(65536)
        verdict = b"stream: Eicar-Sig FOUND\0" if b"EICAR" in buf else b"stream: OK\0"
        conn.sendall(verdict)
        conn.close()

    t = threading.Thread(target=serve)
    t.start()
    assert clamav.scan_bytes(b"xx EICAR xx", path) == ("FOUND", "Eicar-Sig")
    t.join()
    srv.close()


def test_rejects_docx_zip_bomb(sample, settings, monkeypatch):
    from app.pipeline import validate

    monkeypatch.setattr(validate, "MAX_DOCX_UNCOMPRESSED", 1000)
    with pytest.raises(ValidationError, match="unsafe size"):
        validate_upload(sample("sample.docx"), "a.docx", Settings(clamav_enabled=False))


def test_rejects_huge_image(sample, monkeypatch):
    from app.pipeline import validate

    monkeypatch.setattr(validate, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(ValidationError, match="too large"):
        validate_upload(sample("sample.png"), "a.png", Settings(clamav_enabled=False))


def test_rejects_truncated_image(sample, settings):
    data = sample("sample.png")[:60]
    with pytest.raises(ValidationError, match="damaged"):
        validate_upload(data, "a.png", settings)
