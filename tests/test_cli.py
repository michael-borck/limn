"""CLI end-to-end with a faked provider."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from limn import __version__
from limn.cli import app
from limn.providers import GeneratedImage, ImageProvider
from tests.conftest import PNG_BYTES

runner = CliRunner()


def all_output(result) -> str:
    """stdout + stderr regardless of click version's capture behavior."""
    try:
        return result.output + result.stderr
    except (ValueError, AttributeError):
        return result.output


class FakeProvider(ImageProvider):
    name = "fake"

    def __init__(self):
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        return [GeneratedImage(PNG_BYTES) for _ in range(request.count)]


@pytest.fixture
def fake_provider(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr("limn.core.get_provider", lambda name: provider)
    return provider


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_no_args_shows_help(isolated_config):
    result = runner.invoke(app, [])
    assert "generate" in all_output(result)
    assert "serve" in all_output(result)


def test_generate_subcommand_without_prompt_errors(isolated_config):
    result = runner.invoke(app, ["generate"])
    assert result.exit_code == 2


def test_explicit_generate_subcommand(isolated_config, fake_provider):
    _, cwd = isolated_config
    result = runner.invoke(app, ["generate", "a fox", "--provider", "fake"])
    assert result.exit_code == 0, result.output
    assert (cwd / "a-fox.png").exists()


def test_no_provider_is_a_helpful_error(isolated_config, fake_provider):
    result = runner.invoke(app, ["a red bicycle"])
    assert result.exit_code == 2
    assert "provider" in all_output(result).lower()


def test_generate_to_out_file(isolated_config, fake_provider, tmp_path):
    out = tmp_path / "bike.png"
    result = runner.invoke(
        app,
        ["a red bicycle", "--provider", "fake", "-o", str(out), "--seed", "7"],
    )
    assert result.exit_code == 0, result.output
    assert out.read_bytes() == PNG_BYTES
    assert "bike.png" in result.output
    assert fake_provider.requests[0].seed == 7
    assert fake_provider.requests[0].prompt == "a red bicycle"


def test_flags_override_config(isolated_config, fake_provider):
    _, cwd = isolated_config
    (cwd / "limn.yaml").write_text(
        "provider: swarmui\nsize: [512, 512]\ncount: 1\n"
    )
    result = runner.invoke(
        app, ["a fox", "--size", "1024x768", "--count", "2"]
    )
    assert result.exit_code == 0, result.output
    request = fake_provider.requests[0]
    assert request.size == (1024, 768)
    assert request.count == 2
    # Two images -> numbered names derived from the prompt slug.
    assert (cwd / "a-fox.png").exists() or (cwd / "a-fox-1.png").exists()


def test_default_output_name(isolated_config, fake_provider):
    _, cwd = isolated_config
    result = runner.invoke(app, ["A Red Bicycle!", "--provider", "fake"])
    assert result.exit_code == 0, result.output
    assert (cwd / "a-red-bicycle.png").exists()


def test_init_config(isolated_config):
    _, cwd = isolated_config
    result = runner.invoke(app, ["--init-config"])
    assert result.exit_code == 0
    assert (cwd / "limn.yaml").exists()
    # Second run refuses to overwrite.
    result = runner.invoke(app, ["--init-config"])
    assert result.exit_code == 1
