"""Config layering, env expansion, per-provider resolution."""

from __future__ import annotations

import pytest

from limn.config import (
    ConfigurationError,
    expand_env_vars,
    load_config,
    resolve_settings,
    save_example_config,
)


def test_expand_env_vars_embedded(monkeypatch):
    monkeypatch.setenv("LIMN_TEST_TOKEN", "sekrit")
    assert expand_env_vars("Bearer ${LIMN_TEST_TOKEN}") == "Bearer sekrit"
    assert expand_env_vars({"key": "${LIMN_TEST_TOKEN}"}) == {"key": "sekrit"}
    assert expand_env_vars(["${LIMN_TEST_TOKEN}", 3]) == ["sekrit", 3]


def test_expand_env_vars_missing_becomes_empty(monkeypatch):
    monkeypatch.delenv("LIMN_NOPE", raising=False)
    assert expand_env_vars("${LIMN_NOPE}") == ""


def test_defaults_when_no_files(isolated_config):
    cfg = load_config()
    assert cfg["provider"] is None
    assert cfg["size"] == [1024, 1024]
    assert cfg["count"] == 1


def test_home_then_project_layering(isolated_config):
    home, cwd = isolated_config
    (home / ".limn.yaml").write_text(
        "provider: swarmui\nbase_url: https://img.example.org\n"
    )
    (cwd / "limn.yaml").write_text("provider: gemini\n")

    cfg = load_config()
    # Project overrides provider; home's base_url survives.
    assert cfg["provider"] == "gemini"
    assert cfg["base_url"] == "https://img.example.org"


def test_explicit_config_path(isolated_config, tmp_path):
    special = tmp_path / "special.yaml"
    special.write_text("provider: openai\nmodel: dall-e-3\n")
    cfg = load_config(str(special))
    assert cfg["provider"] == "openai"
    assert cfg["model"] == "dall-e-3"


def test_explicit_config_path_missing(isolated_config):
    with pytest.raises(ConfigurationError):
        load_config("does-not-exist.yaml")


def test_invalid_yaml_raises(isolated_config):
    _, cwd = isolated_config
    (cwd / "limn.yaml").write_text("provider: [unclosed\n")
    with pytest.raises(ConfigurationError):
        load_config()


def test_non_mapping_config_raises(isolated_config):
    _, cwd = isolated_config
    (cwd / "limn.yaml").write_text("- just\n- a list\n")
    with pytest.raises(ConfigurationError):
        load_config()


def test_resolve_settings_per_provider_override(isolated_config):
    _, cwd = isolated_config
    (cwd / "limn.yaml").write_text(
        "provider: swarmui\n"
        "model: top-level-model\n"
        "providers:\n"
        "  swarmui:\n"
        "    base_url: https://swarm.example.org\n"
        "  gemini:\n"
        "    model: imagen-4.0-fast-generate-001\n"
    )
    cfg = load_config()

    swarm = resolve_settings(cfg, "swarmui")
    assert swarm["provider"] == "swarmui"
    assert swarm["base_url"] == "https://swarm.example.org"
    assert swarm["model"] == "top-level-model"

    gemini = resolve_settings(cfg, "gemini")
    assert gemini["model"] == "imagen-4.0-fast-generate-001"
    assert gemini["base_url"] is None
    assert "providers" not in gemini


def test_save_example_config(isolated_config):
    path = save_example_config()
    assert path.exists()
    assert "provider: swarmui" in path.read_text()
    with pytest.raises(ConfigurationError):
        save_example_config()
