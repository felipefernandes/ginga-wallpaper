"""Tray helpers and entry-point guards."""

import sys

import pytest

from ginga import tray


def test_icon_image_is_a_square_rgba_with_content():
    img = tray.icon_image()
    assert img.size == (tray.ICON_SIZE, tray.ICON_SIZE) and img.mode == "RGBA"
    assert img.getbbox() is not None  # something was drawn


def test_icon_image_scales_for_the_exe_icon():
    assert tray.icon_image(256).size == (256, 256)


@pytest.mark.skipif(sys.platform != "win32", reason="named mutex is Windows-only")
def test_second_instance_is_refused():
    from ginga.__main__ import _single_instance

    # Own mutex name: the real app may be running on the dev machine.
    name = r"Local\ginga-wallpaper-test"
    first = _single_instance(name)
    assert first is not None
    assert _single_instance(name) is None


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
