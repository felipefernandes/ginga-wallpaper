"""Tray helpers and entry-point guards."""

import sys

import pytest

from ginga import tray


def test_icon_image_is_a_square_rgba_with_content():
    img = tray.icon_image()
    assert img.size == (tray.ICON_SIZE, tray.ICON_SIZE) and img.mode == "RGBA"
    assert img.getbbox() is not None  # something was drawn


@pytest.mark.skipif(sys.platform != "win32", reason="named mutex is Windows-only")
def test_second_instance_is_refused():
    from ginga.__main__ import _single_instance

    first = _single_instance()
    assert first is not None
    assert _single_instance() is None


def test_about_text_credits_author_repo_and_version():
    text = tray.about_text()
    assert "Felipe Fernandes" in text
    assert "github.com/felipefernandes/ginga-wallpaper" in text
    assert "versão" in text


def test_menu_actions_log_errors_instead_of_failing_silently(caplog):
    def boom():
        raise RuntimeError("kaboom")

    tray.safe(boom)()  # must not raise
    assert "kaboom" in caplog.text
