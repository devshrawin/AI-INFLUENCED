"""Core check: metadata AI flags and duplicate detection across applications."""

import io

from PIL import Image, ImageEnhance

from app.config import Settings
from app.pipeline.check import Submission, check_file
from app.pipeline.validate import validate_upload

S = Settings(clamav_enabled=False)


def run(db, data, app_id, applicant, name="file.jpg", doc_type="auto", scheme="Flood relief"):
    vf = validate_upload(data, name, S)
    return check_file(vf, Submission(app_id, applicant, scheme, doc_type), db, S)


def codes(result):
    return {f.code for f in result.flags}


def whatsapp_copy(data, quality=55):
    """Resized, brightened, re-compressed copy: different bytes, same picture."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im = ImageEnhance.Brightness(im.resize((800, 600))).enhance(1.1)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def test_clean_photo(db, sample):
    r = run(db, sample("photo1.jpg"), "APP-1", "citizen-1")
    assert r.level == "none" and r.treated_as == "photo" and r.flags == []
    assert r.note == "No issues found."


def test_same_photo_13_applicants(db, sample):
    """The flood-photo case: the same picture re-used by many people."""
    original = sample("photo1.jpg")
    run(db, original, "APP-1", "citizen-1")
    for i in range(2, 14):
        run(db, whatsapp_copy(original, quality=40 + i), f"APP-{i}", f"citizen-{i}")
    r = run(db, whatsapp_copy(original, quality=70), "APP-14", "citizen-14")
    assert r.level == "high" and "DUPLICATE_PHOTO" in codes(r)
    flag = next(f for f in r.flags if f.code == "DUPLICATE_PHOTO")
    assert "13 other applications" in flag.message
    assert flag.matches[0]["application_id"] in {f"APP-{i}" for i in range(1, 14)}
    assert "please review" in r.note and "not proof" in r.note


def test_exact_same_file(db, sample):
    run(db, sample("photo1.jpg"), "APP-1", "citizen-1")
    r = run(db, sample("photo1.jpg"), "APP-2", "citizen-2")
    assert "DUPLICATE_FILE" in codes(r) and "DUPLICATE_PHOTO" not in codes(r)  # reported once
    assert r.flags[0].matches[0]["distance"] == 0


def test_same_applicant_reupload_not_flagged(db, sample):
    run(db, sample("photo1.jpg"), "APP-1", "citizen-1")
    r = run(db, sample("photo1.jpg"), "APP-2", "citizen-1")
    assert r.level == "none"


def test_different_photos_not_flagged(db, sample):
    run(db, sample("photo1.jpg"), "APP-1", "citizen-1")
    assert run(db, sample("photo2.jpg"), "APP-2", "citizen-2").level == "none"


def test_different_marksheets_not_flagged(db, sample):
    """Same layout, different student: must NOT be called a duplicate."""
    run(db, sample("marksheet1.png"), "APP-1", "student-1")
    r = run(db, sample("marksheet2.png"), "APP-2", "student-2")
    assert r.treated_as == "document" and r.level == "none"


def test_same_marksheet_file_reused(db, sample):
    run(db, sample("marksheet1.png"), "APP-1", "student-1")
    r = run(db, sample("marksheet1.png"), "APP-2", "student-2")
    assert "DUPLICATE_FILE" in codes(r)


def test_platform_can_force_photo(db, sample):
    r = run(db, sample("sample.png"), "APP-1", "c1", doc_type="photo")
    assert r.treated_as == "photo"


def test_signed_ai_credential(db, sample):
    r = run(db, sample("c2pa_ai.jpg"), "APP-1", "citizen-1")
    assert r.level == "high" and "AI_CREDENTIAL" in codes(r)
    assert "TestDiffusion" in r.note


def test_unsigned_ai_metadata_is_review(db):
    img = Image.new("RGB", (400, 300))
    exif = img.getexif()
    exif[0x0131] = "Midjourney v6"
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    r = run(db, buf.getvalue(), "APP-1", "c1")
    assert r.level == "review" and "AI_METADATA" in codes(r)


def test_editing_software_is_info_only(db, sample):
    im = Image.open(io.BytesIO(sample("photo1.jpg")))
    exif = im.getexif()
    exif[0x0131] = "Adobe Photoshop 25.1"
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=exif)
    r = run(db, buf.getvalue(), "APP-1", "c1")
    assert r.level == "none" and "EDITING_SOFTWARE" in codes(r)


def test_documents(db, sample):
    r = run(db, sample("sample.pdf"), "APP-1", "c1", name="m.pdf")
    assert r.treated_as == "document" and r.level == "none"
    r = run(db, sample("sample.docx"), "APP-2", "c2", name="m.docx")
    assert r.level == "none"


def test_result_serialisable(db, sample):
    import json

    run(db, sample("photo1.jpg"), "APP-1", "c1")
    json.dumps(run(db, sample("photo1.jpg"), "APP-2", "c2").to_dict())


def test_fingerprint_stored_once_per_application(db, sample):
    from app.db.models import Fingerprint

    run(db, sample("photo1.jpg"), "APP-1", "c1")
    run(db, sample("photo1.jpg"), "APP-1", "c1")
    assert db.query(Fingerprint).count() == 1
