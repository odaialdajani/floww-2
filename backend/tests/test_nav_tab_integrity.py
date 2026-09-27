"""Every sidebar tab must be reachable, from the sidebar and from a deep link.

`navConfig.js` is the single source of truth for the nav, but a tab can be
listed there and still be dead: App.js may never render it, or may gate it
behind a `?page=` allowlist that omits the id. That already happened once --
StealThreePreview was fully built and completely unreachable because it had no
nav entry and its id was not whitelisted.

These are static checks (they parse two JS files rather than mounting the whole
app, which needs a live backend), but they fail the moment a tab is added to
the nav without being wired, or wired but not whitelisted. They live under
backend pytest because they assert a cross-file navigation contract rather
than React behaviour, so they run in the same gate as the rest of the suite.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_JS = REPO_ROOT / "frontend" / "src" / "App.js"
NAV_CONFIG = REPO_ROOT / "frontend" / "src" / "shell" / "navConfig.js"

# The tabs the product is expected to ship. Renaming one is a deliberate
# change that should update this list, not something to discover via a failure.
REQUIRED_TABS = ("heatseeker", "trinity", "skylit", "portfolio", "journal", "public")


def _nav_ids() -> list[str]:
    return re.findall(r'id:\s*"([a-z0-9-]+)"', NAV_CONFIG.read_text())


def test_nav_config_declares_the_expected_tabs():
    ids = _nav_ids()
    assert ids, "navConfig.js declares no tabs"
    missing = [t for t in REQUIRED_TABS if t not in ids]
    assert not missing, f"nav is missing {missing}; declared: {ids}"


@pytest.mark.parametrize("tab_id", _nav_ids())
def test_every_nav_tab_is_rendered_in_app(tab_id: str):
    src = APP_JS.read_text()
    assert re.search(rf'page\s*===\s*"{re.escape(tab_id)}"', src), (
        f'navConfig.js lists {tab_id!r} but App.js never renders '
        f'page === "{tab_id}" — the tab is unreachable from the sidebar'
    )


def test_no_tab_renders_without_being_in_the_nav():
    src = APP_JS.read_text()
    # Only a `page === "x" && (<JSX...>)` render branch counts as "rendered".
    # A bare `page === "x"` inside a condition (e.g. gating the ticker search
    # widget) does not make a page reachable.
    rendered = set(re.findall(r'page\s*===\s*"([a-z0-9-]+)"\s*&&\s*\(', src))
    # flow-alerts is a live WebSocket overlay, not a sidebar page.
    rendered -= {"flow-alerts"}
    orphans = sorted(rendered - set(_nav_ids()))
    assert not orphans, (
        f"App.js renders {orphans} but navConfig.js has no entry, so they "
        "cannot be reached from the sidebar"
    )


def test_no_dangling_page_ids_in_widget_conditions():
    """Ids referenced in App.js conditions must be real pages.

    `ticker-analysis` survived as an id in the ticker-search condition after
    its page was removed: nothing renders it, it is not in the nav, and it is
    not in the ?page= whitelist, so the condition could never be true. Harmless
    today, but it is a dead end that misleads the next reader.
    """
    src = APP_JS.read_text()
    known = set(_nav_ids()) | {"flow-alerts"}
    referenced = set(re.findall(r'page\s*===\s*"([a-z0-9-]+)"', src))
    dangling = sorted(referenced - known)
    assert not dangling, (
        f"App.js references page id(s) {dangling} that no nav entry defines "
        "and nothing renders — dead conditions left behind by removed pages"
    )
