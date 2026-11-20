"""Tray helpers and entry-point guards."""

import sys

import pytest

from ginga import tray
from ginga.config import load_config


def test_icon_image_is_a_square_rgba_with_content():
    img = tray.icon_image()
    assert img.size == (tray.ICON_SIZE, tray.ICON_SIZE) and img.mode == "RGBA"
    assert img.getbbox() is not None  # something was drawn


def test_open_config_creates_defaults_before_opening(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(tray.os, "startfile", opened.append, raising=False)
    path = tmp_path / "ginga" / "config.toml"

    tray.open_config(path)

    assert opened == [path]
    assert path.exists() and load_config(path).render.fps == 30


@pytest.mark.skipif(sys.platform != "win32", reason="named mutex is Windows-only")
def test_second_instance_is_refused():
    from ginga.__main__ import _single_instance

    first = _single_instance()
    assert first is not None
    assert _single_instance() is None
