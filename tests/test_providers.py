"""Provider clients against faked HTTP."""

from __future__ import annotations

import base64

import pytest

from limn.providers import (
    GenerateRequest,
    ProviderError,
    get_provider,
)
from limn.providers.gemini import GeminiProvider, nearest_aspect_ratio
from limn.providers.openai_compat import OpenAICompatibleProvider, OpenAIProvider
from limn.providers.swarmui import SwarmUIProvider
from tests.conftest import PNG_BYTES, FakeResponse


@pytest.fixture(autouse=True)
def no_provider_env(monkeypatch):
    """Keep the developer's real keys/servers out of provider tests."""
    for var in (
        "SWARMUI_BASE_URL",
        "SWARMUI_TOKEN",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


# --- factory ---------------------------------------------------------------


def test_factory_aliases():
    assert isinstance(get_provider("swarmui"), SwarmUIProvider)
    assert isinstance(get_provider("dalle"), OpenAIProvider)
    assert isinstance(get_provider("imagen"), GeminiProvider)
    assert isinstance(get_provider("OpenAI-Compatible"), OpenAICompatibleProvider)


def test_factory_unknown():
    with pytest.raises(ProviderError, match="Unknown provider"):
        get_provider("midjourney")


# --- swarmui ----------------------------------------------------------------


def test_swarmui_full_flow(monkeypatch):
    calls: list[tuple[str, dict]] = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append((url, json or {}))
        if url.endswith("/API/GetNewSession"):
            return FakeResponse({"session_id": "s-1"})
        return FakeResponse({"images": ["View/local/a.png", "View/local/b.png"]})

    def fake_get(url, headers=None, timeout=None):
        return FakeResponse(content=PNG_BYTES)

    monkeypatch.setattr("limn.providers.swarmui.requests.post", fake_post)
    monkeypatch.setattr("limn.providers.swarmui.requests.get", fake_get)

    request = GenerateRequest(
        prompt="a fox",
        base_url="https://swarm.example.org/",
        size=(1024, 576),
        count=2,
        seed=42,
        negative="blurry",
        model="juggernautXL_v9",
    )
    images = SwarmUIProvider().generate(request)

    assert len(images) == 2
    assert images[0].data == PNG_BYTES
    gen_payload = calls[1][1]
    assert gen_payload["prompt"] == "a fox"
    assert gen_payload["images"] == 2
    assert gen_payload["width"] == 1024
    assert gen_payload["height"] == 576
    assert gen_payload["seed"] == 42
    assert gen_payload["negativeprompt"] == "blurry"
    assert gen_payload["model"] == "juggernautXL_v9"


def test_swarmui_requires_base_url():
    with pytest.raises(ProviderError, match="base_url"):
        SwarmUIProvider().generate(GenerateRequest(prompt="a fox"))


def test_swarmui_no_images_is_error(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        if url.endswith("/API/GetNewSession"):
            return FakeResponse({"session_id": "s-1"})
        return FakeResponse({"images": []})

    monkeypatch.setattr("limn.providers.swarmui.requests.post", fake_post)
    request = GenerateRequest(prompt="a fox", base_url="https://s.example.org")
    with pytest.raises(ProviderError, match="no images"):
        SwarmUIProvider().generate(request)


# --- openai / openai-compatible ----------------------------------------------


def test_openai_b64_response(monkeypatch):
    seen: dict = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen["url"] = url
        seen["json"] = json
        seen["headers"] = headers
        b64 = base64.b64encode(PNG_BYTES).decode()
        return FakeResponse({"data": [{"b64_json": b64}]})

    monkeypatch.setattr("limn.providers.openai_compat.requests.post", fake_post)

    request = GenerateRequest(prompt="a fox", api_key="sk-test", size=(1024, 1024))
    images = OpenAIProvider().generate(request)

    assert images[0].data == PNG_BYTES
    assert seen["url"] == "https://api.openai.com/v1/images/generations"
    assert seen["headers"]["Authorization"] == "Bearer sk-test"
    assert seen["json"]["model"] == "gpt-image-1"
    assert seen["json"]["size"] == "1024x1024"


def test_openai_url_response(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        return FakeResponse({"data": [{"url": "https://cdn.example.org/i.png"}]})

    def fake_get(url, timeout=None):
        return FakeResponse(content=PNG_BYTES)

    monkeypatch.setattr("limn.providers.openai_compat.requests.post", fake_post)
    monkeypatch.setattr("limn.providers.openai_compat.requests.get", fake_get)

    images = OpenAIProvider().generate(GenerateRequest(prompt="x", api_key="k"))
    assert images[0].data == PNG_BYTES


def test_openai_requires_key():
    with pytest.raises(ProviderError, match="API key"):
        OpenAIProvider().generate(GenerateRequest(prompt="a fox"))


def test_openai_surfaces_api_error(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        return FakeResponse(
            {"error": {"message": "billing hard limit"}}, status_code=400
        )

    monkeypatch.setattr("limn.providers.openai_compat.requests.post", fake_post)
    with pytest.raises(ProviderError, match="billing hard limit"):
        OpenAIProvider().generate(GenerateRequest(prompt="x", api_key="k"))


def test_openai_compatible_requires_base_url():
    with pytest.raises(ProviderError, match="base_url"):
        OpenAICompatibleProvider().generate(GenerateRequest(prompt="a fox"))


def test_openai_compatible_no_key_needed(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        assert "Authorization" not in (headers or {})
        b64 = base64.b64encode(PNG_BYTES).decode()
        return FakeResponse({"data": [{"b64_json": b64}]})

    monkeypatch.setattr("limn.providers.openai_compat.requests.post", fake_post)
    request = GenerateRequest(prompt="a fox", base_url="http://localhost:8080/v1")
    images = OpenAICompatibleProvider().generate(request)
    assert images[0].data == PNG_BYTES


# --- gemini -------------------------------------------------------------------


def test_nearest_aspect_ratio():
    assert nearest_aspect_ratio((1024, 1024)) == "1:1"
    assert nearest_aspect_ratio((1920, 1080)) == "16:9"
    assert nearest_aspect_ratio((1080, 1920)) == "9:16"
    assert nearest_aspect_ratio((800, 600)) == "4:3"
    assert nearest_aspect_ratio((600, 800)) == "3:4"


def test_gemini_predict(monkeypatch):
    seen: dict = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen["url"] = url
        seen["json"] = json
        seen["headers"] = headers
        b64 = base64.b64encode(PNG_BYTES).decode()
        return FakeResponse(
            {"predictions": [{"bytesBase64Encoded": b64}]}
        )

    monkeypatch.setattr("limn.providers.gemini.requests.post", fake_post)

    request = GenerateRequest(
        prompt="a fox", api_key="g-key", size=(1920, 1080), count=1
    )
    images = GeminiProvider().generate(request)

    assert images[0].data == PNG_BYTES
    assert seen["url"].endswith("imagen-4.0-fast-generate-001:predict")
    assert seen["headers"]["x-goog-api-key"] == "g-key"
    assert seen["json"]["parameters"] == {"sampleCount": 1, "aspectRatio": "16:9"}
    assert seen["json"]["instances"] == [{"prompt": "a fox"}]


def test_gemini_requires_key():
    with pytest.raises(ProviderError, match="API key"):
        GeminiProvider().generate(GenerateRequest(prompt="a fox"))


def test_gemini_env_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")

    def fake_post(url, json=None, headers=None, timeout=None):
        assert (headers or {}).get("x-goog-api-key") == "env-key"
        b64 = base64.b64encode(PNG_BYTES).decode()
        return FakeResponse({"predictions": [{"bytesBase64Encoded": b64}]})

    monkeypatch.setattr("limn.providers.gemini.requests.post", fake_post)
    images = GeminiProvider().generate(GenerateRequest(prompt="a fox"))
    assert len(images) == 1


def test_gemini_surfaces_api_error(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        return FakeResponse(
            {"error": {"message": "API key not valid"}}, status_code=400
        )

    monkeypatch.setattr("limn.providers.gemini.requests.post", fake_post)
    with pytest.raises(ProviderError, match="API key not valid"):
        GeminiProvider().generate(GenerateRequest(prompt="x", api_key="bad"))
