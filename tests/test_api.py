"""Platform API: /api/v1/check with an API key."""

from app.db.models import AuditLog
from tests.conftest import API_KEY

H = {"X-API-Key": API_KEY}


def post(client, sample, name, app_id, applicant, headers=H, **extra):
    data = {"application_id": app_id, "applicant_id": applicant, **extra}
    return client.post("/api/v1/check", data=data, files={"file": (name, sample(name))}, headers=headers)


def test_requires_api_key(client, sample):
    r = post(client, sample, "photo1.jpg", "A1", "c1", headers={})
    assert r.status_code == 401 and r.json()["error"]
    r = post(client, sample, "photo1.jpg", "A1", "c1", headers={"X-API-Key": "wrong-key-wrong-key"})
    assert r.status_code == 401


def test_check_and_duplicate(client, sample, db):
    r = post(client, sample, "photo1.jpg", "A1", "c1", scheme="Flood 2026", doc_type="photo")
    assert r.status_code == 200
    body = r.json()
    assert body["level"] == "none" and body["treated_as"] == "photo" and "metadata" not in body
    r = post(client, sample, "photo1.jpg", "A2", "c2")
    body = r.json()
    assert body["level"] == "high"
    assert body["flags"][0]["code"] == "DUPLICATE_FILE"
    assert body["flags"][0]["matches"][0]["application_id"] == "A1"
    row = db.query(AuditLog).filter_by(application_id="A2").one()
    assert row.username.startswith("api:") and row.flag_level == "high"
    assert API_KEY not in row.username  # the key itself is never logged


def test_missing_fields_and_bad_file(client, sample):
    r = client.post("/api/v1/check", data={"application_id": "A1"},
                    files={"file": ("p.jpg", sample("photo1.jpg"))}, headers=H)  # fmt: skip
    assert r.status_code == 422 and "applicant_id" in r.json()["error"]
    r = post(client, sample, "fake.png", "A1", "c1")
    assert r.status_code == 422 and "Unsupported" in r.json()["error"]
    r = post(client, sample, "photo1.jpg", "A1", "c1", doc_type="video")
    assert r.status_code == 422


def test_api_disabled_without_keys(client, sample, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "api_keys", "")
    assert post(client, sample, "photo1.jpg", "A1", "c1").status_code == 401


def test_health(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}
