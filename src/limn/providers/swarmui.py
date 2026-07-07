"""SwarmUI native-API provider (self-hosted).

SwarmUI does not speak the OpenAI /v1/images shape, so this uses its
GetNewSession -> GenerateText2Image -> fetch-path flow. Same approach as
slide-stream's SwarmUI provider, reduced to prompt-in / bytes-out.
"""

from __future__ import annotations

import os
from typing import Any

import requests

from limn.providers.base import (
    GeneratedImage,
    GenerateRequest,
    ImageProvider,
    ProviderError,
)

# Model files are listed with their weight-file extension, but the generate
# API wants the bare name (e.g. "juggernautXL_v9", not "...safetensors").
_WEIGHT_EXTENSIONS = (".safetensors", ".ckpt", ".sft", ".gguf")


def _strip_weight_extension(name: str) -> str:
    for ext in _WEIGHT_EXTENSIONS:
        if name.endswith(ext):
            return name[: -len(ext)]
    return name


class SwarmUIProvider(ImageProvider):
    name = "swarmui"

    def _connection(self, request: GenerateRequest) -> tuple[str, dict[str, str]]:
        base_url = request.base_url or os.getenv("SWARMUI_BASE_URL")
        if not base_url:
            raise ProviderError(
                "SwarmUI needs a base_url (config 'base_url', "
                "providers.swarmui.base_url, or SWARMUI_BASE_URL)."
            )
        api_key = request.api_key or os.getenv("SWARMUI_TOKEN")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        return base_url.rstrip("/"), headers

    def list_models(self, request: GenerateRequest) -> list[str]:
        base_url, headers = self._connection(request)
        try:
            session = requests.post(
                f"{base_url}/API/GetNewSession",
                json={},
                headers=headers,
                timeout=30,
            )
            session.raise_for_status()
            session_id = session.json()["session_id"]

            response = requests.post(
                f"{base_url}/API/ListModels",
                json={
                    "session_id": session_id,
                    "path": "",
                    "depth": 5,
                    "subtype": "Stable-Diffusion",
                    "sortBy": "Name",
                },
                headers=headers,
                timeout=60,
            )
            response.raise_for_status()
            files = response.json().get("files") or []
            return [
                _strip_weight_extension(str(f["name"]))
                for f in files
                if isinstance(f, dict) and f.get("name")
            ]
        except (requests.RequestException, KeyError, ValueError) as e:
            raise ProviderError(f"SwarmUI error: {e}") from e

    def generate(self, request: GenerateRequest) -> list[GeneratedImage]:
        base_url, headers = self._connection(request)

        try:
            session = requests.post(
                f"{base_url}/API/GetNewSession",
                json={},
                headers=headers,
                timeout=30,
            )
            session.raise_for_status()
            session_id = session.json()["session_id"]

            width, height = request.size
            payload: dict[str, Any] = {
                "session_id": session_id,
                "prompt": request.prompt,
                "images": request.count,
                "width": width,
                "height": height,
            }
            if request.model:
                payload["model"] = request.model
            if request.seed is not None:
                payload["seed"] = request.seed
            if request.negative:
                payload["negativeprompt"] = request.negative

            gen = requests.post(
                f"{base_url}/API/GenerateText2Image",
                json=payload,
                headers=headers,
                timeout=request.timeout,
            )
            gen.raise_for_status()
            data = gen.json()
            paths = data.get("images")
            if not paths:
                raise ProviderError(f"SwarmUI returned no images ({data})")

            images: list[GeneratedImage] = []
            for path in paths:
                img = requests.get(
                    f"{base_url}/{str(path).lstrip('/')}",
                    headers=headers,
                    timeout=request.timeout,
                )
                img.raise_for_status()
                images.append(GeneratedImage(data=img.content, seed=request.seed))
            return images

        except ProviderError:
            raise
        except (requests.RequestException, KeyError, ValueError) as e:
            raise ProviderError(f"SwarmUI error: {e}") from e
