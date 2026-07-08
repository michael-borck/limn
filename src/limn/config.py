"""Layered configuration for Limn.

Layers, later wins:

1. Built-in defaults
2. ``~/.limn.yaml``  — personal provider + keys, set once
3. ``./limn.yaml``   — per-directory overrides (or an explicit ``--config`` path)
4. CLI flags         — applied by the CLI on top of the loaded config

Secrets are referenced as ``${VAR}`` and expanded from the environment, so no
plaintext keys need to live in config files.
"""

from __future__ import annotations

import copy
import os
import re
from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing."""


# Flat on purpose: Limn does one thing. An optional ``providers:`` mapping
# holds per-provider settings (base_url, model, api_key) so several providers
# can stay configured at once and be swapped with ``provider:`` / --provider.
DEFAULT_CONFIG: dict[str, Any] = {
    "provider": None,
    "base_url": None,
    "model": None,
    "api_key": None,
    "username": None,
    "password": None,
    "size": [1024, 1024],
    "count": 1,
    "seed": None,
    "negative": None,
    "loras": None,
    "cfg_scale": None,
    "steps": None,
    "sampler": None,
    "scheduler": None,
    "timeout": 180,
    "providers": {},
}

_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_env_vars(value: Any) -> Any:
    """Recursively expand ``${VAR}`` references in configuration values."""
    if isinstance(value, str):
        return _ENV_VAR_RE.sub(lambda m: os.getenv(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: expand_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env_vars(item) for item in value]
    return value


def _first_existing(*candidates: Path) -> Path | None:
    for path in candidates:
        if path.exists():
            return path
    return None


def find_home_config() -> Path | None:
    """The user-level config (~/.limn.yaml) — provider + keys, set once."""
    return _first_existing(
        Path.home() / ".limn.yaml",
        Path.home() / ".limn.yml",
    )


def find_project_config() -> Path | None:
    """The directory-level config (./limn.yaml)."""
    return _first_existing(
        Path("./limn.yaml"),
        Path("./limn.yml"),
    )


def _read_config_file(config_file: Path) -> dict[str, Any] | None:
    try:
        with open(config_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigurationError(f"Invalid YAML in {config_file}: {e}") from e
    except OSError as e:
        raise ConfigurationError(f"Error reading {config_file}: {e}") from e
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ConfigurationError(
            f"Config file {config_file} must contain a YAML mapping"
        )
    return data


def merge_configs(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge two config dicts (override wins)."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """Load configuration by layering defaults, home, and project files.

    An explicit ``config_path`` replaces the auto-discovered ./limn.yaml but
    still sits on top of ~/.limn.yaml.
    """
    config = copy.deepcopy(DEFAULT_CONFIG)

    sources: list[Path] = []
    if home_config := find_home_config():
        sources.append(home_config)
    if config_path:
        explicit = Path(config_path)
        if not explicit.exists():
            raise ConfigurationError(f"Configuration file not found: {config_path}")
        sources.append(explicit)
    elif project_config := find_project_config():
        sources.append(project_config)

    for source in sources:
        file_config = _read_config_file(source)
        if file_config:
            config = merge_configs(config, file_config)

    return expand_env_vars(config)


def resolve_settings(config: dict[str, Any], provider: str) -> dict[str, Any]:
    """Effective flat settings for one provider.

    Top-level keys are the base; an entry under ``providers.<name>`` overrides
    them, so a config can keep swarmui, gemini, ... configured side by side.

    The ``<name>`` is normally a canonical provider type (``swarmui``), but a
    block may set ``type:`` to point at a type explicitly — letting you run two
    servers of the same type under distinct labels (e.g. ``swarmui-bearer`` and
    ``swarmui-basic``, both ``type: swarmui``). ``settings['provider']`` keeps
    the label for display; the class is resolved from ``type`` (see core).
    """
    settings = {k: v for k, v in config.items() if k != "providers"}
    per_provider = config.get("providers") or {}
    override = per_provider.get(provider)
    if isinstance(override, dict):
        settings = merge_configs(settings, override)
    settings["provider"] = provider
    return settings


EXAMPLE_CONFIG = """\
# Limn configuration
#
# Layered, later wins:
#   1. built-in defaults
#   2. ~/.limn.yaml   (personal: provider, server URL, API keys — set once)
#   3. ./limn.yaml    (per-directory overrides; or pass --config FILE)
#   4. CLI flags      (e.g. --provider, --size)
#
# Secrets: reference environment variables as ${VAR} — no plaintext keys.

provider: swarmui          # swarmui | openai-compatible | openai | gemini

# Settings shared by whichever provider is active:
size: [1024, 1024]
# count: 1
# seed: 42
# negative: "text, watermark"

# Advanced generation controls (SwarmUI only; other providers warn + ignore):
# loras:                              # applied to every generation
#   - pixel-art-xl:1.0                #   name:weight (weight optional, default 1)
# cfg_scale: 5                        # lower = looser/more stylized (try 4-6)
# steps: 30
# sampler: euler                      # provider-specific sampler name
# scheduler: normal

# Per-provider settings (only the active provider's block is used, so you can
# keep several configured and swap with `provider:` or --provider):
providers:
  swarmui:
    base_url: https://image.example.org
    model: juggernautXL_v9
    # Auth (pick one). Bearer = SwarmUI's own token; Basic = reverse-proxy auth:
    # api_key: "${SWARMUI_TOKEN}"     # -> Authorization: Bearer ...
    # username: admin                 # -> Authorization: Basic ... (with password)
    # password: "${SWARMUI_PASS}"

  # A second SwarmUI server behind HTTP Basic auth, under its own label.
  # Select it with `provider: swarmui-basic` or --provider swarmui-basic:
  # swarmui-basic:
  #   type: swarmui                   # which provider class to use
  #   base_url: https://image2.example.org
  #   username: admin
  #   password: "${SWARMUI_PASS}"

  openai-compatible:                  # LocalAI, or any /v1/images endpoint
    base_url: http://localhost:8080/v1
    model: sdxl

  openai:                             # cloud OpenAI Images
    model: gpt-image-1                # or dall-e-3
    # api_key: "${OPENAI_API_KEY}"    # defaults to the env var anyway

  gemini:                             # Google Imagen (~$0.02/img on Fast)
    model: imagen-4.0-fast-generate-001
    # api_key: "${GEMINI_API_KEY}"    # defaults to the env var anyway
"""


def save_example_config(path: str = "limn.yaml") -> Path:
    """Write an example configuration file and return its path."""
    target = Path(path)
    if target.exists():
        raise ConfigurationError(f"Refusing to overwrite existing {target}")
    target.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    return target
