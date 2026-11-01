from fastapi.testclient import TestClient


def test_index_and_upload(sample, monkeypatch):
    from app.main import create_app
    from app.pipeline.detectors import registry
    from tests.fakes import fake_image, fake_text

    monkeypatch.setattr(registry, "image_detectors", lambda: fake_image(90, 90))
    monkeypatch.setattr(registry, "text_detectors", lambda: fake_text(10, 10))
    client = TestClient(create_app())
    assert client.get("/").status_code == 200
    r = client.post("/check", files={"file": ("sample.png", sample("sample.png"), "image/png")})
    assert r.status_code == 200 and "Likely AI" in r.text and "not proof" in r.text
    r = client.post("/check", files={"file": ("human.txt", sample("human.txt"), "text/plain")})
    assert "Likely Human" in r.text
    r = client.post("/check", files={"file": ("fake.png", sample("fake.png"), "image/png")})
    assert r.status_code == 400
