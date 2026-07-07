"""Google Imagen provider via the Gemini API's REST predict endpoint.

Plain HTTP instead of the google-genai SDK keeps Limn dependency-light.
Imagen takes an aspect ratio rather than exact pixels, so the requested size
is mapped to the nearest supported ratio.
"""

from __future__ import annotations

import base64
import math
import os
from typing import Any

import requests

from limn.providers.base import (
    GeneratedImage,
    GenerateRequest,
    ImageProvider,
    ProviderError,
)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "imagen-4.0-fast-generate-001"

# Aspect ratios the Imagen API accepts.
ASPECT_RATIOS = {
    "1:1": 1 / 1,
    "4:3": 4 / 3,
    "3:4": 3 / 4,
    "16:9": 16 / 9,
    "9:16": 9 / 16,
}


def nearest_aspect_ratio(size: tuple[int, int]) -> str:
    """Map an exact WxH to the closest ratio Imagen supports."""
    width, height = size
    if width <= 0 or height <= 0:
        raise ProviderError(f"Invalid size {width}x{height}")
    target = width / height
    return min(
        ASPECT_RATIOS,
        key=lambda name: abs(math.log(ASPECT_RATIOS[name]) - math.log(target)),
    )


class GeminiProvider(ImageProvider):
    name = "gemini"

    def unsupported(self, request: GenerateRequest) -> list[tuple[str, object]]:
        # The Gemini API's Imagen endpoint accepts neither seed nor negative
        # prompt (both are Vertex-only features).
        return [("--seed", request.seed), ("--negative", request.negative)]

    def _api_key(self, request: GenerateRequest) -> str:
        api_key = (
            request.api_key
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        )
        if not api_key:
            raise ProviderError(
                "Gemini needs an API key (config 'api_key', GEMINI_API_KEY, "
                "or GOOGLE_API_KEY)."
            )
        return api_key

    def list_models(self, request: GenerateRequest) -> list[str]:
        api_key = self._api_key(request)
        base_url = (request.base_url or GEMINI_API_URL).rstrip("/")
        try:
            response = requests.get(
                f"{base_url}/models",
                params={"pageSize": "1000"},
                headers={"x-goog-api-key": api_key},
                timeout=30,
            )
            if not response.ok:
                raise ProviderError(
                    f"Imagen returned {response.status_code}: "
                    f"{_error_detail(response)}"
                )
            names = [
                str(m["name"]).removeprefix("models/")
                for m in response.json().get("models") or []
                if isinstance(m, dict) and m.get("name")
            ]
            return sorted(n for n in names if "imagen" in n.lower())
        except ProviderError:
            raise
        except (requests.RequestException, ValueError) as e:
            raise ProviderError(f"Imagen error: {e}") from e

    def generate(self, request: GenerateRequest) -> list[GeneratedImage]:
        self.warn_unsupported(request)
        api_key = self._api_key(request)

        base_url = (request.base_url or GEMINI_API_URL).rstrip("/")
        model = request.model or DEFAULT_MODEL

        payload: dict[str, Any] = {
            "instances": [{"prompt": request.prompt}],
            "parameters": {
                "sampleCount": request.count,
                "aspectRatio": nearest_aspect_ratio(request.size),
            },
        }

        try:
            response = requests.post(
                f"{base_url}/models/{model}:predict",
                json=payload,
                headers={
                    "x-goog-api-key": api_key,
                    "Content-Type": "application/json",
                },
                timeout=request.timeout,
            )
            if not response.ok:
                detail = _error_detail(response)
                raise ProviderError(
                    f"Imagen returned {response.status_code}: {detail}"
                )
            predictions = response.json().get("predictions") or []
            images = [
                GeneratedImage(data=base64.b64decode(p["bytesBase64Encoded"]))
                for p in predictions
                if p.get("bytesBase64Encoded")
            ]
            if not images:
                raise ProviderError("Imagen returned no images")
            return images

        except ProviderError:
            raise
        except (requests.RequestException, KeyError, ValueError) as e:
            raise ProviderError(f"Imagen error: {e}") from e


def _error_detail(response: requests.Response) -> str:
    """Best-effort human-readable error from a Google API response."""
    try:
        body = response.json()
        return body.get("error", {}).get("message") or str(body)
    except ValueError:
        return response.text[:300]
