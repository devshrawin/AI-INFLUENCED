"""PoC page: no login, AI tab and duplicates tab."""


def _post(client, path, sample, *names, field="file"):
    files = [(field, (n, sample(n), "image/jpeg")) for n in names]
    return client.post(path, files=files)


def test_page_open_without_login(client):
    r = client.get("/")
    assert r.status_code == 200 and "AI photo check" in r.text and "Duplicate pictures" in r.text
    assert client.get("/login", follow_redirects=False).status_code == 404


def test_ai_tab_flags_credential(client, sample):
    r = _post(client, "/poc/ai", sample, "c2pa_ai.jpg")
    assert "AI-generated" in r.text and "digitally signed content credential" in r.text


def test_ai_tab_clean_photo_and_nothing_stored(client, sample, db):
    from app.db.models import Fingerprint

    r = _post(client, "/poc/ai", sample, "photo1.jpg")
    assert "No AI signs found" in r.text
    assert db.query(Fingerprint).count() == 0


def test_ai_tab_rejects_fake_file(client, sample):
    r = client.post("/poc/ai", files={"file": ("fake.png", sample("fake.png"), "image/png")})
    assert r.status_code == 400 and "Unsupported file type" in r.text


def test_duplicates_tab_batch_and_reset(client, sample):
    r = _post(client, "/poc/duplicates", sample, "photo1.jpg", "photo2.jpg", "photo1.jpg", field="files")
    assert r.text.count("New picture") == 2 and r.text.count("Duplicate") >= 1
    assert "1</strong> duplicate" in r.text
    again = _post(client, "/poc/duplicates", sample, "photo2.jpg", field="files")
    assert "pill high" in again.text  # remembered from the first batch
    assert "0</strong> pictures" in client.post("/poc/reset").text
    fresh = _post(client, "/poc/duplicates", sample, "photo2.jpg", field="files")
    assert "New picture" in fresh.text


def test_api_still_works(client, sample):
    from tests.conftest import API_KEY

    r = client.post("/api/v1/check", headers={"X-API-Key": API_KEY},
                    data={"application_id": "A", "applicant_id": "P"},
                    files={"file": ("c2pa_ai.jpg", sample("c2pa_ai.jpg"), "image/jpeg")})  # fmt: skip
    assert r.status_code == 200 and r.json()["level"] == "high"


def test_security_headers(client):
    r = client.get("/")
    assert "script-src 'self'" in r.headers["Content-Security-Policy"]
