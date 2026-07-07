"""Provider registry: name -> thin image-generation client."""

from __future__ import annotations

from limn.providers.base import (
    GeneratedImage,
    GenerateRequest,
    ImageProvider,
    ProviderError,
)
from limn.providers.gemini import GeminiProvider
from limn.providers.openai_compat import OpenAICompatibleProvider, OpenAIProvider
from limn.providers.swarmui import SwarmUIProvider

__all__ = [
    "GeneratedImage",
    "GenerateRequest",
    "ImageProvider",
    "ProviderError",
    "PROVIDERS",
    "get_provider",
    "SwarmUIProvider",
    "OpenAIProvider",
    "OpenAICompatibleProvider",
    "GeminiProvider",
]

PROVIDERS: dict[str, type[ImageProvider]] = {
    "swarmui": SwarmUIProvider,
    "openai": OpenAIProvider,
    "dalle": OpenAIProvider,
    "openai-compatible": OpenAICompatibleProvider,
    "gemini": GeminiProvider,
    "imagen": GeminiProvider,
}


def get_provider(name: str) -> ImageProvider:
    """Instantiate a provider by name (aliases: dalle -> openai, imagen -> gemini)."""
    try:
        provider_cls = PROVIDERS[name.lower()]
    except KeyError:
        known = ", ".join(sorted(set(PROVIDERS)))
        raise ProviderError(
            f"Unknown provider '{name}'. Choose from: {known}"
        ) from None
    return provider_cls()
