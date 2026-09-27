"""Offline checks that the browser tests compare the actual captures."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from tests.e2e import test_dashboard_visual as visual


def test_determinism_compares_just_captured_images(monkeypatch, tmp_path):
    baseline, actual = tmp_path / "baseline.png", tmp_path / "old-actual.png"
    baseline.write_bytes(b"same old image")
    actual.write_bytes(b"same old image")
    monkeypatch.setattr(visual, "BASELINE_PATH", baseline)
    monkeypatch.setattr(visual, "ACTUAL_PATH", actual)
    monkeypatch.setattr(visual, "SCREENSHOTS_DIR", tmp_path)
    captures = iter([b"first capture", b"second capture"])

    class Page:
        closed = False

        def close(self):
            self.closed = True

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

        def screenshot(self):
            return next(captures)

    def compare(first, second, diff, tolerance):
        same = Path(first).read_bytes() == Path(second).read_bytes()
        return same, 0.0 if same else 1.0

    monkeypatch.setattr(visual, "_compare_screenshots", compare)
    page = Page()
    context = SimpleNamespace(new_page=lambda: page)
    with pytest.raises(pytest.fail.Exception, match="Non-deterministic"):
        visual.TestDashboardVisual().test_screenshot_determinism(None, context, tmp_path)
    assert page.closed


def test_changed_dimensions_are_not_resized_into_a_pass(monkeypatch, tmp_path):
    import sys

    # The test concerns size validation, before the third-party pixel operation.
    monkeypatch.setitem(sys.modules, "pixelmatch", SimpleNamespace(pixelmatch=lambda *a, **kw: 0))
    first, second, diff = (tmp_path / name for name in ("first.png", "second.png", "diff.png"))
    Image.new("RGBA", (8, 8), "red").save(first)
    Image.new("RGBA", (16, 16), "red").save(second)
    with pytest.raises(ValueError, match="dimensions"):
        visual._compare_screenshots(first, second, diff)


def test_identical_new_captures_do_not_need_a_saved_baseline(monkeypatch, tmp_path):
    monkeypatch.setattr(visual, "BASELINE_PATH", tmp_path / "absent.png")
    closed = []
    page = SimpleNamespace(
        route=lambda *a, **kw: None, goto=lambda *a, **kw: None,
        add_style_tag=lambda *a, **kw: None, wait_for_selector=lambda *a, **kw: None,
        click=lambda *a, **kw: None, wait_for_timeout=lambda *a, **kw: None,
        reload=lambda *a, **kw: None, screenshot=lambda: b"identical captures",
        close=lambda: closed.append(True),
    )
    context = SimpleNamespace(new_page=lambda: page)
    visual.TestDashboardVisual().test_screenshot_determinism(None, context, tmp_path)
    assert closed == [True]
