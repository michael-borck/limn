"""Core: request building, file naming, saving."""

from __future__ import annotations

import pytest

from limn.core import (
    build_request,
    generate,
    image_extension,
    save_images,
    slugify,
)
from limn.providers import GeneratedImage
from tests.conftest import JPEG_BYTES, PNG_BYTES


def test_image_extension_sniffing():
    assert image_extension(PNG_BYTES) == ".png"
    assert image_extension(JPEG_BYTES) == ".jpg"
    assert image_extension(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == ".webp"
    assert image_extension(b"GIF89a...") == ".gif"
    assert image_extension(b"mystery bytes") == ".png"


def test_slugify():
    assert slugify("A red bicycle, against a brick wall!") == (
        "a-red-bicycle-against-a-brick-wall"
    )
    assert slugify("   ") == "image"
    assert len(slugify("x" * 100)) <= 40


def test_build_request_maps_settings():
    req = build_request(
        "a fox",
        {
            "size": [512, 768],
            "count": 2,
            "seed": 42,
            "negative": "text",
            "model": "sdxl",
            "base_url": "http://localhost:8080",
            "api_key": "k",
            "timeout": 60,
        },
    )
    assert req.prompt == "a fox"
    assert req.size == (512, 768)
    assert req.count == 2
    assert req.seed == 42
    assert req.negative == "text"
    assert req.timeout == 60.0


def test_build_request_rejects_bad_size():
    with pytest.raises(ValueError):
        build_request("a fox", {"size": "huge"})


def test_generate_requires_provider():
    with pytest.raises(ValueError, match="No provider configured"):
        generate("a fox", {})


def test_save_default_name_from_prompt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    paths = save_images([GeneratedImage(PNG_BYTES)], "A Red Bicycle!")
    assert [p.name for p in paths] == ["a-red-bicycle.png"]
    assert paths[0].read_bytes() == PNG_BYTES


def test_save_default_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    first = save_images([GeneratedImage(PNG_BYTES)], "fox")
    second = save_images([GeneratedImage(PNG_BYTES)], "fox")
    assert first[0].name == "fox.png"
    assert second[0].name == "fox-2.png"


def test_save_single_to_exact_out(tmp_path):
    out = tmp_path / "nested" / "bike.png"
    paths = save_images([GeneratedImage(PNG_BYTES)], "bike", str(out))
    assert paths == [out]
    assert out.read_bytes() == PNG_BYTES


def test_save_out_without_suffix_sniffs_extension(tmp_path):
    out = tmp_path / "bike"
    paths = save_images([GeneratedImage(JPEG_BYTES)], "bike", str(out))
    assert paths[0].name == "bike.jpg"


def test_save_multiple_numbered(tmp_path):
    out = tmp_path / "fox.png"
    images = [GeneratedImage(PNG_BYTES), GeneratedImage(PNG_BYTES)]
    paths = save_images(images, "fox", str(out))
    assert [p.name for p in paths] == ["fox-1.png", "fox-2.png"]
