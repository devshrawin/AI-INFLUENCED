"""End-to-end web tests: login, roles, CSRF, checks, audit log."""

from app.db.models import AuditLog
from tests.conftest import PASSWORD, csrf_of, login


def _check(client, sample, name, mime, app_id="APP-1", applicant="citizen-1"):
    token = csrf_of(client.get("/").text)
    data = {"application_id": app_id, "applicant_id": applicant}
    return client.post("/check", data=data, files={"file": (name, sample(name), mime)},
                       headers={"X-CSRF-Token": token})  # fmt: skip


def test_pages_require_login(client):
    for path in ("/", "/history", "/admin/users", "/admin/audit"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"


def test_login_and_check(client, make_user, sample, db):
    make_user()
    assert login(client).status_code == 303
    r = _check(client, sample, "photo1.jpg", "image/jpeg")
    assert r.status_code == 200 and "No issues found" in r.text
    r = _check(client, sample, "photo1.jpg", "image/jpeg", app_id="APP-2", applicant="citizen-2")
    assert "Flagged" in r.text and "APP-1" in r.text and "not proof" in r.text
    row = db.query(AuditLog).filter_by(event="check", application_id="APP-2").one()
    assert row.username == "officer1" and row.sha256 and row.flag_level == "high"
    assert row.flags[0]["code"] == "DUPLICATE_FILE"
    assert row.stored_path is None  # files are not kept by default


def test_c2pa_flag_in_page(client, make_user, sample):
    make_user()
    login(client)
    r = _check(client, sample, "c2pa_ai.jpg", "image/jpeg")
    assert "Flagged" in r.text and "digitally signed content credential" in r.text


def test_ids_required(client, make_user, sample):
    make_user()
    login(client)
    r = _check(client, sample, "photo1.jpg", "image/jpeg", app_id=" ", applicant=" ")
    assert r.status_code == 400 and "required" in r.text


def test_rejected_file_is_logged(client, make_user, sample, db):
    make_user()
    login(client)
    assert _check(client, sample, "fake.png", "image/png").status_code == 400
    assert db.query(AuditLog).filter_by(event="rejected").count() == 1


def test_csrf_required(client, make_user, sample):
    make_user()
    login(client)
    data = {"application_id": "A", "applicant_id": "B"}
    r = client.post("/check", data=data, files={"file": ("a.png", sample("sample.png"), "image/png")})
    assert r.status_code == 403
    r = client.post("/check", data=data, files={"file": ("a.png", sample("sample.png"), "image/png")},
                    headers={"X-CSRF-Token": "wrong"})  # fmt: skip
    assert r.status_code == 403


def test_wrong_password_and_lockout(client, make_user, db):
    user = make_user()
    for _ in range(5):
        assert login(client, password="nope-nope-1").status_code == 401
    db.refresh(user)
    assert user.locked_until is not None
    r = login(client)  # correct password, but locked
    assert r.status_code == 403
    assert db.query(AuditLog).filter_by(event="login_failed").count() == 5


def test_unknown_user(client, db):
    assert login(client, username="ghost").status_code == 401


def test_officer_cannot_open_admin(client, make_user):
    make_user()
    login(client)
    assert client.get("/admin/users").status_code == 403
    assert client.get("/admin/audit").status_code == 403


def test_admin_creates_user_and_views_audit(client, make_user, sample, db):
    make_user("boss", role="admin")
    login(client, "boss")
    page = client.get("/admin/users")
    assert page.status_code == 200
    form = {
        "username": "new.officer",
        "role": "officer",
        "auth_source": "local",
        "password": "Temp-pass-999",
        "csrf_token": csrf_of(page.text),
    }
    r = client.post("/admin/users", data=form, follow_redirects=False)
    assert r.status_code == 303
    _check(client, sample, "sample.png", "image/png")
    audit = client.get("/admin/audit?event=check")
    assert audit.status_code == 200 and "sample.png" in audit.text and "APP-1" in audit.text
    csv_text = client.get("/admin/audit.csv").text
    assert "sha256" in csv_text.splitlines()[0] and "user_created" in csv_text
    row_id = db.query(AuditLog).filter_by(event="check").one().id
    assert "APP-1" in client.get(f"/admin/audit/{row_id}").text
    assert client.get("/admin/audit?q=APP-1&level=none").status_code == 200


def test_weak_password_rejected_on_create(client, make_user):
    make_user("boss", role="admin")
    login(client, "boss")
    token = csrf_of(client.get("/admin/users").text)
    r = client.post("/admin/users", data={"username": "x", "role": "officer", "auth_source": "local",
                                          "password": "short", "csrf_token": token})  # fmt: skip
    assert r.status_code == 400 and "at least" in r.text


def test_must_change_password_flow(client, make_user):
    make_user(must_change=True)
    r = login(client)
    assert r.headers["location"] == "/account/password"
    assert client.get("/", follow_redirects=False).headers["location"] == "/account/password"
    page = client.get("/account/password")
    new = "Brand-new-pass-1"
    form = {"current": PASSWORD, "new": new, "confirm": new, "csrf_token": csrf_of(page.text)}
    r = client.post("/account/password", data=form)
    assert "Password changed" in r.text
    assert client.get("/", follow_redirects=False).status_code == 200


def test_logout(client, make_user):
    make_user()
    login(client)
    token = csrf_of(client.get("/").text)
    client.post("/logout", data={"csrf_token": token})
    assert client.get("/", follow_redirects=False).status_code == 303


def test_security_headers(client):
    r = client.get("/login")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"


def test_rate_limit(client, make_user, sample):
    from app.api.limiter import limiter

    make_user()
    login(client)
    limiter.enabled = True
    codes = [_check(client, sample, "sample.png", "image/png").status_code for _ in range(32)]
    assert 429 in codes and codes[0] == 200


def test_store_uploads_and_retention(client, make_user, sample, db, monkeypatch, tmp_path):
    import os
    import time

    from app.config import get_settings
    from app.services.retention import purge_old_uploads

    settings = get_settings()
    monkeypatch.setattr(settings, "store_uploads", True)
    monkeypatch.setattr(settings, "upload_dir", tmp_path)
    make_user()
    login(client)
    _check(client, sample, "sample.png", "image/png")
    row = db.query(AuditLog).filter_by(event="check").one()
    assert row.stored_path and os.path.exists(row.stored_path)
    assert purge_old_uploads(settings) == 0  # still fresh
    assert purge_old_uploads(settings, now=time.time() + 25 * 3600) == 1
    db.refresh(row)
    assert row.stored_path is None and not any(tmp_path.iterdir())
