"""Web UI API: session lifecycle, save-to-disk, token auth."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from limn.providers import GeneratedImage, ImageProvider
from limn.serve import create_app
from tests.conftest import PNG_BYTES


class FakeProvider(ImageProvider):
    name = "fake"

    def generate(self, request):
        return [
            GeneratedImage(PNG_BYTES, seed=request.seed)
            for _ in range(request.count)
        ]

    def list_models(self, request):
        return [f"model-from-{request.base_url or 'default'}"]


class ExplodingProvider(ImageProvider):
    name = "boom"

    def generate(self, request):
        from limn.providers import ProviderError

        raise ProviderError("backend on fire")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("limn.core.get_provider", lambda name: FakeProvider())
    app = create_app({"provider": "swarmui"}, out_dir=tmp_path / "saved")
    return TestClient(app)


def test_index_serves_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Limn" in response.text


def test_config_endpoint(client):
    data = client.get("/api/config").json()
    assert data["provider"] == "swarmui"
    assert "gemini" in data["providers"]


def test_generate_view_delete_lifecycle(client):
    created = client.post(
        "/api/generate", json={"prompt": "a fox", "count": 2, "seed": 9}
    ).json()["images"]
    assert len(created) == 2
    assert created[0]["prompt"] == "a fox"
    assert created[0]["seed"] == 9

    listed = client.get("/api/images").json()["images"]
    assert [item["id"] for item in listed] == [item["id"] for item in created]

    image = client.get(f"/api/images/{created[0]['id']}")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content == PNG_BYTES

    assert client.delete(f"/api/images/{created[0]['id']}").status_code == 200
    assert client.get(f"/api/images/{created[0]['id']}").status_code == 404
    assert len(client.get("/api/images").json()["images"]) == 1


def test_models_endpoint(client):
    data = client.post("/api/models", json={}).json()
    assert data == {"models": ["model-from-default"], "provider": "swarmui"}
    # Overrides pass through outside demo mode.
    data = client.post(
        "/api/models", json={"base_url": "https://sw.example.org"}
    ).json()
    assert data["models"] == ["model-from-https://sw.example.org"]


def test_generate_validates_input(client):
    assert (
        client.post("/api/generate", json={"prompt": ""}).status_code == 422
    )
    assert (
        client.post(
            "/api/generate", json={"prompt": "x", "size": "huge"}
        ).status_code
        == 400
    )


def test_generate_requires_some_provider(tmp_path, monkeypatch):
    monkeypatch.setattr("limn.core.get_provider", lambda name: FakeProvider())
    app = create_app({}, out_dir=tmp_path)
    client = TestClient(app)
    response = client.post("/api/generate", json={"prompt": "a fox"})
    assert response.status_code == 400
    assert "provider" in response.json()["detail"].lower()


def test_provider_failure_is_502(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "limn.core.get_provider", lambda name: ExplodingProvider()
    )
    app = create_app({"provider": "boom"}, out_dir=tmp_path)
    response = TestClient(app).post("/api/generate", json={"prompt": "a fox"})
    assert response.status_code == 502
    assert "backend on fire" in response.json()["detail"]


def test_save_writes_to_out_dir(client, tmp_path):
    item = client.post("/api/generate", json={"prompt": "A Red Fox!"}).json()[
        "images"
    ][0]
    saved = client.post(f"/api/images/{item['id']}/save", json={}).json()
    path = tmp_path / "saved" / "a-red-fox.png"
    assert saved["path"] == str(path)
    assert path.read_bytes() == PNG_BYTES

    # Saving again never overwrites.
    again = client.post(f"/api/images/{item['id']}/save", json={}).json()
    assert again["path"].endswith("a-red-fox-2.png")


def test_save_sanitizes_filename(client, tmp_path):
    item = client.post("/api/generate", json={"prompt": "fox"}).json()[
        "images"
    ][0]
    saved = client.post(
        f"/api/images/{item['id']}/save",
        json={"filename": "../../evil"},
    ).json()
    assert saved["path"] == str(tmp_path / "saved" / "evil.png")

    bad = client.post(
        f"/api/images/{item['id']}/save", json={"filename": "..."}
    )
    assert bad.status_code == 400


def test_token_gates_everything(tmp_path, monkeypatch):
    monkeypatch.setattr("limn.core.get_provider", lambda name: FakeProvider())
    app = create_app({"provider": "swarmui"}, token="s3cret", out_dir=tmp_path)
    client = TestClient(app)

    assert client.get("/").status_code == 401
    assert client.get("/api/images").status_code == 401
    assert (
        client.post("/api/generate", json={"prompt": "x"}).status_code == 401
    )

    # Query token works and plants a cookie for subsequent calls.
    page = client.get("/?token=s3cret")
    assert page.status_code == 200
    assert client.get("/api/images").status_code == 200

    # Bearer header works too.
    bare = TestClient(create_app({"provider": "swarmui"}, token="s3cret"))
    assert (
        bare.get(
            "/api/images", headers={"Authorization": "Bearer s3cret"}
        ).status_code
        == 200
    )
    assert (
        bare.get(
            "/api/images", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
