"""Limn CLI: `limn "a red bicycle" -o bike.png`, plus `limn serve`."""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console
from rich.markup import escape
from typer.core import TyperGroup

from limn import __version__
from limn.config import ConfigurationError, load_config, resolve_settings
from limn.config import save_example_config as _save_example_config
from limn.core import generate as _generate
from limn.core import list_loras as _list_loras
from limn.core import list_models as _list_models
from limn.core import (
    metadata_for,
    parse_size,
    read_prompts,
    save_images,
    write_metadata,
)
from limn.providers import LoraInfo, ProviderError

console = Console()
err_console = Console(stderr=True, style="bold red")


class DefaultCommandGroup(TyperGroup):
    """Route bare invocations to `generate` so `limn "a prompt"` just works.

    `limn serve ...` and `limn generate ...` hit their commands normally;
    anything else (a prompt, or generate's options like --init-config) is
    prefixed with `generate`.
    """

    default_command = "generate"
    _root_tokens = {"-h", "--help", "-V", "--version"}

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        if args and args[0] not in self.commands and args[0] not in self._root_tokens:
            args = [self.default_command, *args]
        return super().parse_args(ctx, args)


app = typer.Typer(
    cls=DefaultCommandGroup,
    add_completion=False,
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"limn {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Print version and exit.",
    ),
) -> None:
    """Limn — type a description, get an image. Bring your own provider."""
    del version  # handled by the eager callback


@app.command()
def generate(
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
    lora: list[str] = typer.Option(
        None,
        "--lora",
        help="LoRA as name[:weight], repeatable (SwarmUI only). "
        "e.g. --lora pixel-art-xl:1.0",
        show_default=False,
    ),
    cfg_scale: float = typer.Option(
        None, "--cfg", help="CFG / guidance scale (if supported).",
        show_default=False,
    ),
    steps: int = typer.Option(
        None, "--steps", help="Sampling steps (if supported).",
        show_default=False,
    ),
    sampler: str = typer.Option(
        None, "--sampler", help="Sampler name (provider-specific).",
        show_default=False,
    ),
    scheduler: str = typer.Option(
        None, "--scheduler", help="Scheduler name (provider-specific).",
        show_default=False,
    ),
    out: str = typer.Option(
        None, "--out", "-o", help="Output file (default: derived from prompt).",
        show_default=False,
    ),
    from_file: str = typer.Option(
        None,
        "--from",
        help="Read prompts from a file (one per line, '-' for stdin); "
        "each is generated and auto-named.",
        show_default=False,
    ),
    metadata: bool = typer.Option(
        False,
        "--metadata",
        "-M",
        help="Write a <image>.json sidecar of the generation params.",
    ),
    config: str = typer.Option(
        None, "--config", "-c", help="Config file (default: ./limn.yaml).",
        show_default=False,
    ),
    init_config: bool = typer.Option(
        False, "--init-config", help="Write an example ./limn.yaml and exit."
    ),
) -> None:
    """Turn a text description into an image (the default command).

    Configure once in ~/.limn.yaml (provider, server URL / API key), then:

        limn "a red bicycle against a brick wall" -o bike.png

    Batch a list of prompts (one per line, auto-named):

        limn --from prompts.txt
    """
    try:
        if init_config:
            path = _save_example_config()
            console.print(f"Wrote example config: [bold]{path}[/bold]")
            raise typer.Exit()

        if from_file and prompt:
            err_console.print("Give a prompt or --from FILE, not both.")
            raise typer.Exit(code=2)
        if from_file and out:
            err_console.print("--out can't be used with --from (names are derived).")
            raise typer.Exit(code=2)
        if not from_file and not prompt:
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
        if lora:
            settings["loras"] = list(lora)  # _parse_loras handles name:weight
        if cfg_scale is not None:
            settings["cfg_scale"] = cfg_scale
        if steps is not None:
            settings["steps"] = steps
        if sampler is not None:
            settings["sampler"] = sampler
        if scheduler is not None:
            settings["scheduler"] = scheduler

        prompts = read_prompts(from_file) if from_file else [prompt]
        for item in prompts:
            _run_one(item, settings, out, metadata, str(provider_name))

    except (ConfigurationError, ProviderError, ValueError) as e:
        err_console.print(str(e))
        raise typer.Exit(code=1) from None


def _run_one(
    prompt: str,
    settings: dict[str, Any],
    out: str | None,
    metadata: bool,
    provider_name: str,
) -> None:
    """Generate, save, and (optionally) sidecar one prompt."""
    with console.status(f"Generating with {provider_name}...", spinner="dots"):
        images = _generate(prompt, settings)
    paths = save_images(images, prompt, out)
    for path, image in zip(paths, images, strict=True):
        console.print(f"Saved: [bold green]{path}[/bold green]")
        if metadata:
            sidecar = write_metadata(path, metadata_for(prompt, settings, image))
            console.print(f"  metadata: [dim]{sidecar}[/dim]")


@app.command()
def models(
    provider: str = typer.Option(
        None, "--provider", "-p", help="Provider to ask (default: configured).",
        show_default=False,
    ),
    config: str = typer.Option(
        None, "--config", "-c", help="Config file (default: ./limn.yaml).",
        show_default=False,
    ),
    loras: bool = typer.Option(
        False,
        "--loras",
        help="List LoRAs instead, with trigger words where the server has them.",
    ),
) -> None:
    """List the models (or, with --loras, the LoRAs) your provider offers."""
    try:
        cfg = load_config(config)
        provider_name = provider or cfg.get("provider")
        if not provider_name:
            err_console.print(
                "No provider configured. Pass --provider or set one in ~/.limn.yaml."
            )
            raise typer.Exit(code=2)
        settings = resolve_settings(cfg, str(provider_name))
        if loras:
            _print_loras(_list_loras(settings))
            return
        names = _list_models(settings)
        if not names:
            console.print("[dim]No models reported.[/dim]")
        for name in names:
            console.print(name)
    except (ConfigurationError, ProviderError, ValueError) as e:
        err_console.print(str(e))
        raise typer.Exit(code=1) from None


def _clip(text: str, limit: int = 160) -> str:
    """Some servers store Civitai's full trained-word dump as the trigger
    phrase; keep the listing scannable (the real token leads the list)."""
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _print_loras(infos: list[LoraInfo]) -> None:
    """One LoRA per block: name, then whatever metadata the server has."""
    if not infos:
        console.print("[dim]No LoRAs reported.[/dim]")
        return
    for info in infos:
        console.print(f"[bold]{escape(info.name)}[/bold]")
        if info.trigger_phrase:
            console.print(
                f"  trigger: [cyan]{escape(_clip(info.trigger_phrase))}[/cyan]"
            )
        if info.description:
            console.print(f"  [dim]{escape(_clip(info.description))}[/dim]")


@app.command()
def serve(
    host: str = typer.Option(
        "127.0.0.1", "--host", help="Address to bind (127.0.0.1 = local only)."
    ),
    port: int = typer.Option(5466, "--port", help="Port to listen on."),
    token: str | None = typer.Option(
        None,
        "--token",
        help="Access token; generated automatically when binding non-locally.",
        show_default=False,
    ),
    out_dir: str = typer.Option(
        ".", "--out-dir", help="Directory Save writes images into."
    ),
    config: str = typer.Option(
        None, "--config", "-c", help="Config file (default: ./limn.yaml).",
        show_default=False,
    ),
    no_browser: bool = typer.Option(
        False, "--no-browser", help="Don't auto-open the browser."
    ),
    demo: bool = typer.Option(
        False,
        "--demo",
        help="Demo mode (or LIMN_DEMO=1): no token, rate-limited, "
        "Save disabled — nothing stored server-side.",
    ),
) -> None:
    r"""Run the local web UI (needs: pip install 'limn\[serve]')."""
    import os
    import secrets
    import threading
    import webbrowser
    from pathlib import Path

    try:
        import uvicorn

        from limn.serve import create_app
    except ImportError:
        err_console.print(
            "The web UI needs extra dependencies: pip install 'limn[serve]'"
        )
        raise typer.Exit(code=1) from None

    try:
        cfg = load_config(config)
    except ConfigurationError as e:
        err_console.print(str(e))
        raise typer.Exit(code=1) from None

    demo = demo or os.getenv("LIMN_DEMO", "").lower() in ("1", "true", "yes")
    local = host in ("127.0.0.1", "localhost", "::1")
    if demo:
        # Friction-free by design: bounded by rate limits, not a token.
        token = None
        console.print(
            "[bold]Demo mode[/bold]: no token, rate-limited, nothing stored."
        )
    elif token is None and not local:
        # Never expose an unauthenticated instance beyond localhost.
        token = secrets.token_urlsafe(16)
        console.print(f"Generated access token: [bold]{token}[/bold]")

    application = create_app(cfg, token=token, out_dir=Path(out_dir), demo=demo)

    url = f"http://{host}:{port}/" + (f"?token={token}" if token else "")
    console.print(f"Limn web UI: [bold green]{url}[/bold green]  (Ctrl+C to stop)")
    if not no_browser and local:
        threading.Timer(0.8, webbrowser.open, args=[url]).start()

    uvicorn.run(application, host=host, port=port, log_level="warning")
