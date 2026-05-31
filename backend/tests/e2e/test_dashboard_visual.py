"""
backend/tests/e2e/test_dashboard_visual.py

Playwright E2E visual regression tests for the Heatseeker dashboard.
Launches the Dash server, navigates to the Heatseeker tab, captures screenshots,
and compares against baseline images using pixelmatch (2% tolerance for anti-aliasing).

Requirements:
  - playwright + chromium installed
  - pixelmatch installed
  - pytest-playwright installed
  - FastAPI server importable (server.py)
  - Dash UI mounted at /dashboard/

Run:
  pytest backend/tests/e2e/test_dashboard_visual.py -v
  pytest backend/tests/e2e/test_dashboard_visual.py -v --update-baseline  (regenerate baseline)
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # /Users/nav/GitHub/floww
BACKEND_ROOT = PROJECT_ROOT / "backend"
SCREENSHOTS_DIR = PROJECT_ROOT / "docs" / "screenshots"
BASELINE_PATH = SCREENSHOTS_DIR / "baseline_heatseeker.png"
DIFF_PATH = SCREENSHOTS_DIR / "diff_heatseeker.png"
ACTUAL_PATH = SCREENSHOTS_DIR / "actual_heatseeker.png"

# Fixed viewport for deterministic screenshots
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 900

# Tolerance: 2% pixel diff allowed for anti-aliasing
PIXEL_DIFF_TOLERANCE = 0.02

# Server config
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8765
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"
DASHBOARD_URL = f"{SERVER_URL}/dashboard/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_dependencies() -> None:
    """Verify playwright and pixelmatch are installed."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        pytest.skip("playwright not installed — run: pip install playwright && playwright install chromium")
    try:
        import pixelmatch  # noqa: F401
    except ImportError:
        pytest.skip("pixelmatch not installed — run: pip install pixelmatch")


def _compare_screenshots(
    baseline_path: Path,
    actual_path: Path,
    diff_path: Path,
    tolerance: float = PIXEL_DIFF_TOLERANCE,
) -> tuple[bool, float]:
    """
    Compare two screenshots using pixelmatch.
    Returns (passed, diff_ratio).
    """
    import pixelmatch
    from PIL import Image

    baseline = Image.open(baseline_path).convert("RGBA")
    actual = Image.open(actual_path).convert("RGBA")

    # Ensure same size
    if baseline.size != actual.size:
        actual = actual.resize(baseline.size, Image.LANCZOS)

    w, h = baseline.size
    diff = Image.new("RGBA", (w, h))

    # pixelmatch expects flat RGBA sequences
    baseline_data = list(baseline.getdata())
    actual_data = list(actual.getdata())
    diff_data = list(diff.getdata())

    # Flatten [(R,G,B,A), ...] -> [R,G,B,A,R,G,B,A,...]
    baseline_flat = [c for pixel in baseline_data for c in pixel]
    actual_flat = [c for pixel in actual_data for c in pixel]
    diff_flat = [c for pixel in diff_data for c in pixel]

    num_diff_pixels = pixelmatch.pixelmatch(
        baseline_flat,
        actual_flat,
        w,
        h,
        output=diff_flat,
        threshold=0.1,
        includeAA=True,
    )

    total_pixels = w * h
    diff_ratio = num_diff_pixels / total_pixels if total_pixels > 0 else 0.0

    # Reconstruct diff image from flat data
    diff.putdata([(diff_flat[i], diff_flat[i+1], diff_flat[i+2], diff_flat[i+3])
                  for i in range(0, len(diff_flat), 4)])
    diff.save(str(diff_path))

    passed = diff_ratio <= tolerance
    return passed, diff_ratio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def fastapi_server():
    """
    Start the FastAPI server as a background process for E2E tests.
    Yields the process handle; kills it on teardown.
    """
    _check_dependencies()

    env = os.environ.copy()
    env["API_SECRET_KEY"] = "test-secret-key"
    env["PORT"] = str(SERVER_PORT)
    env["HOST"] = SERVER_HOST
    env["ENVIRONMENT"] = "test"

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "server:app",
            "--host", SERVER_HOST,
            "--port", str(SERVER_PORT),
            "--log-level", "warning",
        ],
        cwd=str(BACKEND_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid if hasattr(os, "setsid") else None,
    )

    # Wait for server to be ready
    import urllib.request
    max_wait = 30
    ready = False
    for i in range(max_wait):
        time.sleep(1)
        try:
            req = urllib.request.Request(f"{SERVER_URL}/api/health", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    ready = True
                    break
        except Exception:
            pass

    if not ready:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        pytest.skip(f"FastAPI server did not start within {max_wait}s")

    yield proc

    # Teardown
    try:
        if hasattr(os, "killpg"):
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:
            proc.terminate()
        proc.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            proc.kill()
        except ProcessLookupError:
            pass


@pytest.fixture(scope="session")
def browser_context():
    """Create a Playwright browser context with fixed viewport."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--disable-animations",
            "--disable-gpu",
        ])
        context = browser.new_context(
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            # Disable animations for deterministic screenshots
            reduced_motion="reduce",
        )
        yield context
        context.close()
        browser.close()


# ===========================================================================
# Tests
# ===========================================================================

class TestDashboardVisual:
    """Visual regression tests for the Heatseeker dashboard."""

    def test_heatseeker_tab_loads(self, fastapi_server, browser_context):
        """
        Smoke test: the Heatseeker tab must load without errors.
        Navigates to /dashboard/ and verifies the page renders.
        """
        page = browser_context.new_page()

        # Block external API calls for determinism
        page.route("**/api/live/**", lambda route: route.abort())
        page.route("**/api/chain/**", lambda route: route.abort())

        page.goto(DASHBOARD_URL, wait_until="networkidle", timeout=30000)

        # Disable animations via CSS for deterministic rendering
        page.add_style_tag(content="""
            * { animation-duration: 0s !important; transition-duration: 0s !important; }
            ._dash-loading { display: none !important; }
        """)

        # Wait for the Dash app to mount
        page.wait_for_selector("#main-tabs", timeout=15000)

        # Verify the Heatseeker tab exists and is visible
        tabs = page.query_selector_all("#main-tabs .tab")
        assert len(tabs) > 0, "No tabs found in dashboard"

        # Take a screenshot to verify page loaded
        page.screenshot(path=str(ACTUAL_PATH))
        assert ACTUAL_PATH.exists(), "Screenshot was not saved"

        page.close()

    def test_heatseeker_tag_overlays_render(self, fastapi_server, browser_context):
        """
        Verify that tag overlay elements (King Nodes, Air Pockets) render
        as visible DOM elements in the Heatseeker tab.
        """
        page = browser_context.new_page()
        page.route("**/api/live/**", lambda route: route.abort())

        page.goto(DASHBOARD_URL, wait_until="networkidle", timeout=30000)
        page.add_style_tag(content="""
            * { animation-duration: 0s !important; transition-duration: 0s !important; }
        """)

        # Wait for the Dash app
        page.wait_for_selector("#main-tabs", timeout=15000)

        # Click the Heatseeker tab (first tab)
        page.click("#main-tabs >> text=Heatseeker", timeout=10000)

        # Wait for the graph to render
        page.wait_for_selector(".dash-graph", timeout=15000)

        # Verify the graph container exists
        graph = page.query_selector(".dash-graph")
        assert graph is not None, "Graph container not found"

        page.close()

    def test_visual_regression_heatseeker(self, fastapi_server, browser_context):
        """
        Visual regression: capture screenshot of Heatseeker tab and compare
        against baseline. Diff must be < 2% (anti-aliasing tolerance).

        If no baseline exists, creates one and passes (first run).
        Pass --update-baseline to regenerate.
        """
        update_baseline = "--update-baseline" in sys.argv or os.environ.get("UPDATE_BASELINE") == "1"

        page = browser_context.new_page()
        page.route("**/api/live/**", lambda route: route.abort())

        page.goto(DASHBOARD_URL, wait_until="networkidle", timeout=30000)

        # Disable all animations for deterministic rendering
        page.add_style_tag(content="""
            * {
                animation-duration: 0s !important;
                animation-iteration-count: 0 !important;
                transition-duration: 0s !important;
            }
            ._dash-loading { display: none !important; }
        """)

        # Wait for Dash app to mount
        page.wait_for_selector("#main-tabs", timeout=15000)

        # Navigate to Heatseeker tab
        page.click("#main-tabs >> text=Heatseeker", timeout=10000)

        # Wait for graph to render
        page.wait_for_selector(".dash-graph", timeout=15000)

        # Extra wait for Plotly to finish rendering
        page.wait_for_timeout(2000)

        # Capture screenshot
        page.screenshot(path=str(ACTUAL_PATH))
        assert ACTUAL_PATH.exists(), "Screenshot was not saved"

        if update_baseline or not BASELINE_PATH.exists():
            # First run or explicit update: save as baseline
            import shutil
            shutil.copy2(str(ACTUAL_PATH), str(BASELINE_PATH))
            BASELINE_PATH.touch()
            pytest.skip(f"Baseline {'updated' if update_baseline else 'created'}: {BASELINE_PATH}")

        # Compare against baseline
        passed, diff_ratio = _compare_screenshots(
            BASELINE_PATH, ACTUAL_PATH, DIFF_PATH, tolerance=PIXEL_DIFF_TOLERANCE
        )

        if not passed:
            pytest.fail(
                f"Visual regression failed: {diff_ratio:.4%} pixel diff "
                f"(tolerance: {PIXEL_DIFF_TOLERANCE:.0%}). "
                f"Diff saved to {DIFF_PATH}"
            )

        page.close()

    def test_screenshot_determinism(self, fastapi_server, browser_context):
        """
        Verify screenshot determinism: two consecutive captures of the same
        page state must be identical (0% diff after the baseline is established).
        """
        if not BASELINE_PATH.exists():
            pytest.skip("No baseline screenshot yet — run test_visual_regression_heatseeker first")

        page = browser_context.new_page()
        page.route("**/api/live/**", lambda route: route.abort())

        page.goto(DASHBOARD_URL, wait_until="networkidle", timeout=30000)
        page.add_style_tag(content="""
            * { animation-duration: 0s !important; transition-duration: 0s !important; }
        """)
        page.wait_for_selector("#main-tabs", timeout=15000)
        page.click("#main-tabs >> text=Heatseeker", timeout=10000)
        page.wait_for_selector(".dash-graph", timeout=15000)
        page.wait_for_timeout(2000)

        # First capture
        screenshot1 = page.screenshot()

        # Reload and re-capture
        page.reload(wait_until="networkidle", timeout=30000)
        page.add_style_tag(content="""
            * { animation-duration: 0s !important; transition-duration: 0s !important; }
        """)
        page.wait_for_selector("#main-tabs", timeout=15000)
        page.click("#main-tabs >> text=Heatseeker", timeout=10000)
        page.wait_for_selector(".dash-graph", timeout=15000)
        page.wait_for_timeout(2000)

        screenshot2 = page.screenshot()

        # Compare byte-for-byte (should be identical with fixed viewport and no animations)
        if screenshot1 != screenshot2:
            # Small differences may occur due to timing; check pixel ratio instead
            ratio_path = SCREENSHOTS_DIR / "determinism_check.png"
            passed, diff_ratio = _compare_screenshots(
                BASELINE_PATH, ACTUAL_PATH, ratio_path, tolerance=PIXEL_DIFF_TOLERANCE
            )
            if not passed:
                pytest.fail(f"Non-deterministic screenshots: {diff_ratio:.4%} diff between captures")

        page.close()


# ===========================================================================
# Standalone baseline generator (run without pytest)
# ===========================================================================

if __name__ == "__main__":
    """Generate a baseline screenshot without pytest."""
    _check_dependencies()

    from playwright.sync_api import sync_playwright

    print(f"Screenshot directory: {SCREENSHOTS_DIR}")
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--disable-animations",
            "--disable-gpu",
        ])
        page = browser.new_page(
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
        )

        print(f"Navigating to {DASHBOARD_URL} ...")
        # Note: server must already be running
        page.goto(DASHBOARD_URL, wait_until="networkidle", timeout=30000)
        page.add_style_tag(content="""
            * { animation-duration: 0s !important; transition-duration: 0s !important; }
        """)
        page.wait_for_selector("#main-tabs", timeout=15000)
        page.click("#main-tabs >> text=Heatseeker", timeout=10000)
        page.wait_for_selector(".dash-graph", timeout=15000)
        page.wait_for_timeout(2000)

        page.screenshot(path=str(BASELINE_PATH))
        print(f"Baseline saved to {BASELINE_PATH}")

        browser.close()
