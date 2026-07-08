"""SwarmUI native-API provider (self-hosted).

SwarmUI does not speak the OpenAI /v1/images shape, so this uses its
GetNewSession -> GenerateText2Image -> fetch-path flow. Same approach as
slide-stream's SwarmUI provider, reduced to prompt-in / bytes-out.
"""

from __future__ import annotations

import base64
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
        # Two auth styles, auto-detected: HTTP Basic (a reverse proxy in front
        # of SwarmUI) takes precedence when a username+password pair is given;
        # otherwise a bearer token (SwarmUI's own token). Neither -> no header.
        api_key = request.api_key or os.getenv("SWARMUI_TOKEN")
        username = request.username or os.getenv("SWARMUI_USER")
        password = request.password or os.getenv("SWARMUI_PASS")
        headers: dict[str, str] = {}
        if username and password:
            token = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {token}"
        elif api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return base_url.rstrip("/"), headers

    def _known_loras(
        self, base_url: str, headers: dict[str, str], session_id: str
    ) -> set[str] | None:
        """LoRA names the server registers, lowercased; None if unknowable.

        Best-effort: a failed lookup returns None so validation is skipped
        rather than blocking a generation that would otherwise succeed. The
        server registers a LoRA under its filename minus extension, sometimes
        with a subfolder prefix — index both the full path and its basename.
        """
        try:
            response = requests.post(
                f"{base_url}/API/ListModels",
                json={
                    "session_id": session_id,
                    "path": "",
                    "depth": 10,
                    "subtype": "LoRA",
                    "sortBy": "Name",
                },
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            files = response.json().get("files") or []
        except (requests.RequestException, KeyError, ValueError):
            return None
        known: set[str] = set()
        for f in files:
            if isinstance(f, dict) and f.get("name"):
                name = _strip_weight_extension(str(f["name"]))
                known.add(name.lower())
                known.add(name.rsplit("/", 1)[-1].lower())
        return known

    def _validate_loras(
        self,
        request: GenerateRequest,
        base_url: str,
        headers: dict[str, str],
        session_id: str,
    ) -> None:
        """Fail loudly on a typo'd LoRA (SwarmUI silently no-ops unknown ones)."""
        if not request.loras:
            return
        known = self._known_loras(base_url, headers, session_id)
        if known is None:
            return  # couldn't enumerate; don't block generation
        for name, _ in request.loras:
            candidate = _strip_weight_extension(name).lower()
            if candidate not in known and candidate.rsplit("/", 1)[-1] not in known:
                raise ProviderError(f"LoRA not found on server: {name}")

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

            if request.loras:
                self._validate_loras(request, base_url, headers, session_id)
                # SwarmUI wants comma-separated, index-aligned names + weights.
                payload["loras"] = ",".join(n for n, _ in request.loras)
                payload["loraweights"] = ",".join(
                    f"{w:g}" for _, w in request.loras
                )
            if request.cfg_scale is not None:
                payload["cfgscale"] = request.cfg_scale
            if request.steps is not None:
                payload["steps"] = request.steps
            if request.sampler:
                payload["sampler"] = request.sampler
            if request.scheduler:
                payload["scheduler"] = request.scheduler

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
