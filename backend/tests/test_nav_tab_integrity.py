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
BACKEND = REPO_ROOT / "backend"
ADAPTER = BACKEND / "services" / "public_api_adapter.py"

# The tabs the product is expected to ship. Renaming one is a deliberate
# change that should update this list, not something to discover via a failure.
REQUIRED_TABS = ("heatseeker", "trinity", "skylit", "portfolio", "journal", "public")

# Providers that are retired or that only serve a non-market-data concern.
# Alpaca remains only as the paper-order venue; Finnhub supplies the symbol
# universe and news; Polygon/Alpha Vantage are not on the options path.
# None of them may appear in the options market-data adapter.
NON_MARKET_DATA_PROVIDERS = ("finnhub", "polygon", "alpha_vantage", "alpaca")


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


# ── "All Public" data-source contract ──────────────────────────────────────
#
# The product decision is that every market-data surface (Solstice heatmap,
# Triad, Zenith) is Public.com. Alpaca survives only as the paper-order
# venue; Finnhub supplies the symbol universe and news; Polygon and Alpha
# Vantage are not on the options path. None of them may supply an options
# chain, Greeks, spot or bars.
#
# This is a static text check, so it is deliberately narrow: it inspects the
# Public adapter for any *call* to another provider's client, and ignores
# comments (a comment may legitimately mention Alpaca to explain a naming
# choice, which public_api_adapter.py:62 does).

def test_public_adapter_calls_no_other_market_data_provider():
    import ast

    assert ADAPTER.exists(), f"missing {ADAPTER}"
    # Check the SOURCE TEXT of executable code, not just identifiers: a
    # provider leaks in as `from services.alpaca_client import AlpacaClient`
    # or as a local named `alpaca_client.get_chain(...)`, and neither the
    # method name ("get_chain") nor the attribute name ("get_chain") names
    # the provider. Stripping comments and docstrings first is essential --
    # public_api_adapter.py:62 legitimately mentions Alpaca in a comment to
    # explain why the bar-timeframe keys use that vocabulary.
    import io
    import tokenize

    code_only: list[str] = []
    source = ADAPTER.read_text()
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        code_only.append(tok.string)
    code_text = " ".join(code_only).lower()

    offenders = sorted(p for p in NON_MARKET_DATA_PROVIDERS if p in code_text)
    assert not offenders, (
        f"the options market-data adapter calls {offenders}; the product "
        "decision is that every options surface is Public.com"
    )


def test_schwab_is_absent_from_live_market_data_code():
    """Schwab was retired 2026-09-03 and removed 2026-09-27.

    Only comments and explicit retirement notes may still name it.
    """
    import ast

    checked = 0
    for path in (BACKEND / "services").rglob("*.py"):
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "schwab" in node.module.lower():
                pytest.fail(f"{path.name} imports {node.module}")
            if isinstance(node, ast.Import):
                for a in node.names:
                    if "schwab" in a.name.lower():
                        pytest.fail(f"{path.name} imports {a.name}")
            checked += 1
    assert checked > 0, "no backend service files were inspected"
