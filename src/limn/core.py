"""Core: turn settings + prompt into image files on disk."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from limn.providers import GeneratedImage, GenerateRequest, get_provider

_SIZE_RE = re.compile(r"^(\d+)\s*[xX]\s*(\d+)$")


def parse_size(value: str) -> tuple[int, int]:
    """Parse '1024x1024' (or a bare '1024' meaning square) into (w, h)."""
    value = value.strip()
    if value.isdigit():
        side = int(value)
        return side, side
    match = _SIZE_RE.match(value)
    if not match:
        raise ValueError(f"Size must look like 1024x1024 (got {value!r})")
    return int(match.group(1)), int(match.group(2))


def build_request(prompt: str, settings: dict[str, Any]) -> GenerateRequest:
    """Build a provider request from resolved settings."""
    size = settings.get("size") or [1024, 1024]
    if isinstance(size, (list, tuple)) and len(size) == 2:
        width, height = int(size[0]), int(size[1])
    else:
        raise ValueError(f"size must be [width, height], got {size!r}")

    seed = settings.get("seed")
    return GenerateRequest(
        prompt=prompt,
        size=(width, height),
        count=int(settings.get("count") or 1),
        seed=int(seed) if seed is not None else None,
        negative=settings.get("negative") or None,
        model=settings.get("model") or None,
        base_url=settings.get("base_url") or None,
        api_key=settings.get("api_key") or None,
        timeout=float(settings.get("timeout") or 180),
    )


def _provider_for(settings: dict[str, Any]):
    provider_name = settings.get("provider")
    if not provider_name:
        raise ValueError(
            "No provider configured. Set 'provider:' in ~/.limn.yaml "
            "(run 'limn --init-config' for a template) or pass --provider."
        )
    return get_provider(str(provider_name))


def generate(prompt: str, settings: dict[str, Any]) -> list[GeneratedImage]:
    """Generate images for a prompt using the provider named in settings."""
    return _provider_for(settings).generate(build_request(prompt, settings))


def list_models(settings: dict[str, Any]) -> list[str]:
    """Model names offered by the provider named in settings."""
    return _provider_for(settings).list_models(build_request("", settings))


def image_extension(data: bytes) -> str:
    """File extension from magic bytes (providers return raw image blobs)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8"):
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return ".png"


def slugify(text: str, max_length: int = 40) -> str:
    """Filesystem-safe slug of a prompt for default output names."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = slug[:max_length].rstrip("-")
    return slug or "image"


def unique_path(path: Path) -> Path:
    """Avoid clobbering existing files by appending -2, -3, ..."""
    if not path.exists():
        return path
    for i in range(2, 1000):
        candidate = path.with_name(f"{path.stem}-{i}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Could not find a free filename near {path}")


def save_images(
    images: list[GeneratedImage], prompt: str, out: str | None = None
) -> list[Path]:
    """Write image bytes to disk and return the saved paths.

    - no --out: <prompt-slug>.png in the cwd (never overwrites; -2, -3, ...)
    - --out with one image: exactly that path
    - --out with several: stem-1.ext, stem-2.ext, ...
    """
    paths: list[Path] = []
    if out is None:
        base = Path(slugify(prompt))
        for image in images:
            target = unique_path(base.with_suffix(image_extension(image.data)))
            target.write_bytes(image.data)
            paths.append(target)
        return paths

    out_path = Path(out)
    if out_path.parent != Path("."):
        out_path.parent.mkdir(parents=True, exist_ok=True)

    if len(images) == 1:
        target = out_path if out_path.suffix else out_path.with_suffix(
            image_extension(images[0].data)
        )
        target.write_bytes(images[0].data)
        return [target]

    for i, image in enumerate(images, start=1):
        suffix = out_path.suffix or image_extension(image.data)
        target = out_path.with_name(f"{out_path.stem}-{i}{suffix}")
        target.write_bytes(image.data)
        paths.append(target)
    return paths
