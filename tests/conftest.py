"""Shared test fixtures."""

from __future__ import annotations

from typing import Any

import pytest
import requests

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fakepixels"
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"fakepixels"


class FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(
        self,
        json_data: Any = None,
        status_code: int = 200,
        content: bytes = b"",
        text: str = "",
    ):
        self._json = json_data
        self.status_code = status_code
        self.content = content
        self.text = text or (str(json_data) if json_data is not None else "")

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def json(self) -> Any:
        if self._json is None:
            raise ValueError("No JSON")
        return self._json

    def raise_for_status(self) -> None:
        if not self.ok:
            raise requests.HTTPError(f"HTTP {self.status_code}")


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """No real home/project config files leak into the test."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()
    monkeypatch.setattr("pathlib.Path.home", staticmethod(lambda: home))
    monkeypatch.chdir(cwd)
    return home, cwd
