"""Limn CLI: `limn "a red bicycle" -o bike.png`."""

from __future__ import annotations

import re

import typer
from rich.console import Console

from limn import __version__
from limn.config import ConfigurationError, load_config, resolve_settings
from limn.config import save_example_config as _save_example_config
from limn.core import generate, save_images
from limn.providers import ProviderError

console = Console()
err_console = Console(stderr=True, style="bold red")

app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)

_SIZE_RE = re.compile(r"^(\d+)\s*[xX]\s*(\d+)$")


def parse_size(value: str) -> tuple[int, int]:
    """Parse '1024x1024' (or a bare '1024' meaning square) into (w, h)."""
    value = value.strip()
    if value.isdigit():
        side = int(value)
        return side, side
    match = _SIZE_RE.match(value)
    if not match:
        raise typer.BadParameter(
            f"Size must look like 1024x1024 (got {value!r})"
        )
    return int(match.group(1)), int(match.group(2))


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"limn {__version__}")
        raise typer.Exit()


@app.command()
def main(
    prompt: str = typer.Argument(
        None,
        help="Text description of the image to generate.",
        show_default=False,
    ),
    provider: str = typer.Option(
        None,
        "--provider",
        "-p",
        help="Image provider: swarmui, openai-compatible, openai, gemini.",
        show_default=False,
    ),
    model: str = typer.Option(
        None, "--model", "-m", help="Model name (provider-specific).",
        show_default=False,
    ),
    size: str = typer.Option(
        None, "--size", "-s", help="Image size, e.g. 1024x1024.",
        show_default=False,
    ),
    count: int = typer.Option(
        None, "--count", "-n", min=1, max=10, help="Number of images.",
        show_default=False,
    ),
    seed: int = typer.Option(
        None, "--seed", help="Seed for reproducibility (if supported).",
        show_default=False,
    ),
    negative: str = typer.Option(
        None, "--negative", help="Negative prompt (if supported).",
        show_default=False,
    ),
    out: str = typer.Option(
        None, "--out", "-o", help="Output file (default: derived from prompt).",
        show_default=False,
    ),
    config: str = typer.Option(
        None, "--config", "-c", help="Config file (default: ./limn.yaml).",
        show_default=False,
    ),
    init_config: bool = typer.Option(
        False, "--init-config", help="Write an example ./limn.yaml and exit."
    ),
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Print version and exit.",
    ),
) -> None:
    """Turn a text description into an image, with the provider you chose.

    Configure once in ~/.limn.yaml (provider, server URL / API key), then:

        limn "a red bicycle against a brick wall" -o bike.png
    """
    del version  # handled by the eager callback

    try:
        if init_config:
            path = _save_example_config()
            console.print(f"Wrote example config: [bold]{path}[/bold]")
            raise typer.Exit()

        if not prompt:
            err_console.print("Give me a prompt, e.g.: limn \"a red bicycle\"")
            raise typer.Exit(code=2)

        cfg = load_config(config)
        provider_name = provider or cfg.get("provider")
        if not provider_name:
            err_console.print(
                "No provider configured. Set 'provider:' in ~/.limn.yaml "
                "(limn --init-config writes a template) or pass --provider."
            )
            raise typer.Exit(code=2)

        settings = resolve_settings(cfg, str(provider_name))
        if model is not None:
            settings["model"] = model
        if size is not None:
            settings["size"] = list(parse_size(size))
        if count is not None:
            settings["count"] = count
        if seed is not None:
            settings["seed"] = seed
        if negative is not None:
            settings["negative"] = negative

        with console.status(
            f"Generating with {provider_name}...", spinner="dots"
        ):
            images = generate(prompt, settings)
        paths = save_images(images, prompt, out)
        for path in paths:
            console.print(f"Saved: [bold green]{path}[/bold green]")

    except (ConfigurationError, ProviderError, ValueError) as e:
        err_console.print(str(e))
        raise typer.Exit(code=1) from None
