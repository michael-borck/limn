"""Core: request building, file naming, saving."""

from __future__ import annotations

import pytest

from limn.core import (
    _parse_loras,
    build_request,
    generate,
    image_extension,
    metadata_for,
    parse_size,
    read_prompts,
    save_images,
    slugify,
    write_metadata,
)
from limn.providers import GeneratedImage
from tests.conftest import JPEG_BYTES, PNG_BYTES


def test_parse_size():
    assert parse_size("1024x1024") == (1024, 1024)
    assert parse_size("1920X1080") == (1920, 1080)
    assert parse_size("512") == (512, 512)
    assert parse_size(" 640 x 480 ") == (640, 480)


def test_parse_size_rejects_garbage():
    with pytest.raises(ValueError):
        parse_size("huge")


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


def test_parse_loras_forms():
    assert _parse_loras(["pixel-art-xl"]) == [("pixel-art-xl", 1.0)]
    assert _parse_loras(["pixel-art-xl:0.8"]) == [("pixel-art-xl", 0.8)]
    assert _parse_loras([{"name": "x", "weight": 0.5}]) == [("x", 0.5)]
    assert _parse_loras([{"name": "x"}]) == [("x", 1.0)]
    assert _parse_loras([]) is None
    assert _parse_loras(None) is None


def test_parse_loras_bad_entry():
    with pytest.raises(ValueError):
        _parse_loras([123])


def test_build_request_maps_advanced_and_auth():
    req = build_request(
        "a fox",
        {
            "username": "admin",
            "password": "pw",
            "loras": ["pixel-art-xl:0.9"],
            "cfg_scale": 5,
            "steps": 30,
            "sampler": "euler",
            "scheduler": "normal",
        },
    )
    assert req.username == "admin"
    assert req.password == "pw"
    assert req.loras == [("pixel-art-xl", 0.9)]
    assert req.cfg_scale == 5.0
    assert req.steps == 30
    assert req.sampler == "euler"
    assert req.scheduler == "normal"


def test_build_request_advanced_default_none():
    req = build_request("a fox", {})
    assert req.loras is None
    assert req.cfg_scale is None
    assert req.steps is None
    assert req.username is None


def test_read_prompts_from_file(tmp_path):
    f = tmp_path / "prompts.txt"
    f.write_text("a fox\n\n# a comment\n  a bear  \n")
    assert read_prompts(str(f)) == ["a fox", "a bear"]


def test_read_prompts_missing_file():
    with pytest.raises(ValueError, match="not found"):
        read_prompts("/no/such/file.txt")


def test_read_prompts_empty(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("# only comments\n\n")
    with pytest.raises(ValueError, match="No prompts"):
        read_prompts(str(f))


def test_metadata_for_records_set_params():
    settings = {
        "provider": "swarmui-basic",
        "type": "swarmui",
        "model": "juggernautXL_v9",
        "size": [512, 768],
        "seed": None,
        "loras": ["pixel-art-xl:1.0"],
        "cfg_scale": 5,
        "negative": None,
    }
    meta = metadata_for("a fox", settings, GeneratedImage(PNG_BYTES, seed=42))
    assert meta["prompt"] == "a fox"
    assert meta["provider"] == "swarmui-basic"
    assert meta["type"] == "swarmui"
    assert meta["model"] == "juggernautXL_v9"
    assert meta["size"] == [512, 768]
    assert meta["seed"] == 42  # from the generated image
    assert meta["loras"] == ["pixel-art-xl:1.0"]
    assert meta["cfg_scale"] == 5
    assert "negative" not in meta  # None-valued fields are dropped


def test_write_metadata_sidecar(tmp_path):
    img = tmp_path / "fox.png"
    img.write_bytes(PNG_BYTES)
    sidecar = write_metadata(img, {"prompt": "a fox"})
    assert sidecar.name == "fox.png.json"
    assert "a fox" in sidecar.read_text()


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
