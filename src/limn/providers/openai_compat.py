"""OpenAI Images providers: the real API and any compatible /v1/images endpoint.

Both talk plain HTTP to ``{base_url}/images/generations`` — no SDK needed.
``openai`` defaults base_url to the real API and requires a key;
``openai-compatible`` requires a base_url (LocalAI, a1111 shims, ...) and
treats the key as optional, exactly the split slide-stream uses so a stray
OPENAI_API_KEY never silently sends prompts to the wrong server.
"""

from __future__ import annotations

import base64
import os

import requests

from limn.providers.base import (
    GeneratedImage,
    GenerateRequest,
    ImageProvider,
    ProviderError,
)

OPENAI_API_URL = "https://api.openai.com/v1"


class OpenAIProvider(ImageProvider):
    name = "openai"

    default_base_url: str | None = OPENAI_API_URL
    default_model = "gpt-image-1"
    require_api_key = True

    def unsupported(self, request: GenerateRequest) -> list[tuple[str, object]]:
        # The /v1/images API has no seed or negative-prompt parameters, nor the
        # SwarmUI-only LoRA / sampler knobs.
        return [
            ("--seed", request.seed),
            ("--negative", request.negative),
            *self._advanced_unsupported(request),
        ]

    def _base_url(self, request: GenerateRequest) -> str:
        base_url = request.base_url or self.default_base_url
        if not base_url:
            raise ProviderError(
                f"Provider '{self.name}' needs a base_url (config 'base_url', "
                f"providers.{self.name}.base_url, or OPENAI_BASE_URL)."
            )
        return base_url.rstrip("/")

    def _api_key(self, request: GenerateRequest) -> str | None:
        api_key = request.api_key or os.getenv("OPENAI_API_KEY")
        if not api_key and self.require_api_key:
            raise ProviderError(
                "OpenAI needs an API key (config 'api_key' or OPENAI_API_KEY)."
            )
        return api_key

    def _filter_models(self, ids: list[str]) -> list[str]:
        # The real OpenAI /models lists every chat model too; keep image ones.
        return [i for i in ids if "image" in i or "dall-e" in i]

    def list_models(self, request: GenerateRequest) -> list[str]:
        base_url = self._base_url(request)
        api_key = self._api_key(request)
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        try:
            response = requests.get(
                f"{base_url}/models", headers=headers, timeout=30
            )
            if not response.ok:
                raise ProviderError(
                    f"{self.name} returned {response.status_code}: "
                    f"{_error_detail(response)}"
                )
            ids = [
                str(item["id"])
                for item in response.json().get("data") or []
                if isinstance(item, dict) and item.get("id")
            ]
            return self._filter_models(sorted(ids))
        except ProviderError:
            raise
        except (requests.RequestException, ValueError) as e:
            raise ProviderError(f"{self.name} error: {e}") from e

    def generate(self, request: GenerateRequest) -> list[GeneratedImage]:
        self.warn_unsupported(request)
        base_url = self._base_url(request)
        api_key = self._api_key(request)

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        width, height = request.size
        payload = {
            "model": request.model or self.default_model,
            "prompt": request.prompt,
            "n": request.count,
            "size": f"{width}x{height}",
        }

        try:
            response = requests.post(
                f"{base_url}/images/generations",
                json=payload,
                headers=headers,
                timeout=request.timeout,
            )
            if not response.ok:
                detail = _error_detail(response)
                raise ProviderError(
                    f"{self.name} returned {response.status_code}: {detail}"
                )
            items = response.json().get("data") or []
            if not items:
                raise ProviderError(f"{self.name} returned no image data")

            images: list[GeneratedImage] = []
            for item in items:
                b64 = item.get("b64_json")
                url = item.get("url")
                if b64:
                    images.append(GeneratedImage(data=base64.b64decode(b64)))
                elif url:
                    img = requests.get(url, timeout=request.timeout)
                    img.raise_for_status()
                    images.append(GeneratedImage(data=img.content))
                else:
                    raise ProviderError(
                        f"{self.name} returned neither b64_json nor url"
                    )
            return images

        except ProviderError:
            raise
        except (requests.RequestException, ValueError) as e:
            raise ProviderError(f"{self.name} error: {e}") from e


class OpenAICompatibleProvider(OpenAIProvider):
    name = "openai-compatible"

    default_base_url = None  # must be configured; never default to real OpenAI
    default_model = "stable-diffusion"
    require_api_key = False  # local servers usually don't check

    def _filter_models(self, ids: list[str]) -> list[str]:
        # A local server lists exactly what it hosts; don't second-guess it.
        return ids

    def _base_url(self, request: GenerateRequest) -> str:
        base_url = request.base_url or os.getenv("OPENAI_BASE_URL")
        if not base_url:
            raise ProviderError(
                "openai-compatible needs a base_url (config 'base_url', "
                "providers.openai-compatible.base_url, or OPENAI_BASE_URL). "
                "For the real OpenAI API use provider 'openai'."
            )
        return base_url.rstrip("/")


def _error_detail(response: requests.Response) -> str:
    """Best-effort human-readable error from an OpenAI-style response."""
    try:
        body = response.json()
        return body.get("error", {}).get("message") or str(body)
    except ValueError:
        return response.text[:300]
