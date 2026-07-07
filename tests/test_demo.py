"""Demo mode: friction-free but bounded, and truly non-storing."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from limn.providers import GeneratedImage, ImageProvider
from limn.serve import create_app
from tests.conftest import PNG_BYTES


class RecordingProvider(ImageProvider):
    name = "fake"

    def __init__(self):
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return [GeneratedImage(PNG_BYTES) for _ in range(request.count)]


@pytest.fixture
def provider(monkeypatch):
    recorder = RecordingProvider()
    monkeypatch.setattr("limn.core.get_provider", lambda name: recorder)
    return recorder


def demo_client(provider, tmp_path, **kwargs) -> TestClient:
    config = {"provider": "swarmui", "model": "server-model"}
    app = create_app(config, out_dir=tmp_path, demo=True, **kwargs)
    return TestClient(app)


def test_demo_needs_no_token_even_if_one_is_passed(provider, tmp_path):
    app = create_app({"provider": "swarmui"}, token="secret", demo=True)
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert client.get("/api/images").status_code == 200


def test_demo_advertised_in_config(provider, tmp_path):
    data = demo_client(provider, tmp_path).get("/api/config").json()
    assert data["demo"] is True
    assert data["limits"]["images_per_hour"] > 0


def test_demo_locks_provider_model_count_and_size(provider, tmp_path):
    client = demo_client(provider, tmp_path)
    response = client.post(
        "/api/generate",
        json={
            "prompt": "a fox",
            "provider": "openai",  # ignored: locked to server config
            "model": "gpt-image-1",  # ignored
            "count": 8,  # capped to 1
            "size": "4096x4096",  # clamped to 1024
        },
    )
    assert response.status_code == 200
    items = response.json()["images"]
    assert len(items) == 1
    assert items[0]["provider"] == "swarmui"

    request = provider.requests[0]
    assert request.model == "server-model"
    assert request.count == 1
    assert request.size == (1024, 1024)


def test_demo_rate_limit(provider, tmp_path):
    client = demo_client(provider, tmp_path, demo_images_per_hour=2)
    assert client.post("/api/generate", json={"prompt": "1"}).status_code == 200
    assert client.post("/api/generate", json={"prompt": "2"}).status_code == 200
    blocked = client.post("/api/generate", json={"prompt": "3"})
    assert blocked.status_code == 429
    assert "pip install limn" in blocked.json()["detail"]


def test_demo_save_disabled_download_works(provider, tmp_path):
    client = demo_client(provider, tmp_path)
    item = client.post("/api/generate", json={"prompt": "a fox"}).json()[
        "images"
    ][0]

    save = client.post(f"/api/images/{item['id']}/save", json={})
    assert save.status_code == 403
    assert not any(tmp_path.iterdir())  # truly nothing on disk

    download = client.get(f"/api/images/{item['id']}?download=1")
    assert download.status_code == 200
    assert "attachment" in download.headers["content-disposition"]
    assert download.content == PNG_BYTES


def test_demo_images_expire(provider, tmp_path):
    client = demo_client(provider, tmp_path, demo_ttl_seconds=0)
    item = client.post("/api/generate", json={"prompt": "a fox"}).json()[
        "images"
    ][0]
    # TTL of zero: gone by the next request.
    assert client.get("/api/images").json()["images"] == []
    assert client.get(f"/api/images/{item['id']}").status_code == 404


def test_non_demo_untouched(provider, tmp_path):
    app = create_app({"provider": "swarmui"}, out_dir=tmp_path)
    client = TestClient(app)
    data = client.get("/api/config").json()
    assert data["demo"] is False
    assert "limits" not in data
    # Count and provider overrides still work outside demo.
    response = client.post(
        "/api/generate", json={"prompt": "a fox", "count": 3}
    )
    assert len(response.json()["images"]) == 3
