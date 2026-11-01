from fastapi.testclient import TestClient


def test_index_and_upload(sample):
    from app.main import create_app

    client = TestClient(create_app())
    assert client.get("/").status_code == 200
    r = client.post("/check", files={"file": ("sample.png", sample("sample.png"), "image/png")})
    assert r.status_code == 200 and "png" in r.text
    r = client.post("/check", files={"file": ("fake.png", sample("fake.png"), "image/png")})
    assert r.status_code == 400
