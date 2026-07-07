"""Provider abstraction: a prompt goes in, image bytes come out.

Providers are thin clients over one backend each. They raise ProviderError on
any failure — Limn is an image tool, so it fails loudly rather than degrading
to a placeholder.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from rich.console import Console

err_console = Console(stderr=True, style="yellow")


class ProviderError(Exception):
    """Raised when a provider cannot generate images."""


@dataclass
class GenerateRequest:
    """Everything a provider needs for one generation."""

    prompt: str
    size: tuple[int, int] = (1024, 1024)
    count: int = 1
    seed: int | None = None
    negative: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    timeout: float = 180.0


@dataclass
class GeneratedImage:
    """One generated image plus whatever the backend reported about it."""

    data: bytes
    seed: int | None = None


class ImageProvider(ABC):
    """One backend: turn a GenerateRequest into image bytes."""

    name: str = "base"

    @abstractmethod
    def generate(self, request: GenerateRequest) -> list[GeneratedImage]:
        """Generate ``request.count`` images. Raises ProviderError on failure."""
        raise NotImplementedError

    def list_models(self, request: GenerateRequest) -> list[str]:
        """Model names this backend offers (prompt in ``request`` is unused).

        Raises ProviderError on failure or when the backend can't enumerate.
        """
        raise ProviderError(f"Provider '{self.name}' cannot list models.")

    def warn_unsupported(self, request: GenerateRequest) -> None:
        """Tell the user (stderr) about request fields this backend ignores."""
        for label, value in self.unsupported(request):
            if value is not None:
                err_console.print(
                    f"Note: provider '{self.name}' does not support "
                    f"{label}; ignoring."
                )

    def unsupported(self, request: GenerateRequest) -> list[tuple[str, object]]:
        """(label, value) pairs of request fields this backend ignores."""
        return []
