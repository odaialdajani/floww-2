"""
backend/tests/services/research/test_extract_code_links.py

Unit tests for scripts/extract_code_links.py — pure-function regex extraction
plus the file-level orchestrator. No network, no real files touched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add repo root so scripts.extract_code_links is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from scripts.extract_code_links import (  # noqa: E402
    _strip_trailing_punctuation,
    extract_candidates,
    extract_code_urls,
    find_discovery_files,
    load_discoveries,
)

# ────────────────────────────────────────────────────────────────────────────
# CODE_URL_RE / extract_code_urls
# ────────────────────────────────────────────────────────────────────────────


def test_finds_github_url():
    abstract = "Code is at https://github.com/user/repo for reproducibility."
    assert extract_code_urls(abstract) == ["https://github.com/user/repo"]


def test_finds_gitlab_url():
    abstract = "See https://gitlab.com/user/proj for the implementation."
    assert extract_code_urls(abstract) == ["https://gitlab.com/user/proj"]


def test_finds_bitbucket_url():
    abstract = "code: https://bitbucket.org/team/repo."
    assert extract_code_urls(abstract) == ["https://bitbucket.org/team/repo"]


def test_strips_trailing_period():
    abstract = "Available at https://github.com/owen8877/RLOP."
    assert extract_code_urls(abstract) == ["https://github.com/owen8877/RLOP"]


def test_strips_trailing_comma_and_paren():
    abstract = "Code (https://github.com/x/y), see also https://github.com/a/b."
    assert extract_code_urls(abstract) == [
        "https://github.com/x/y",
        "https://github.com/a/b",
    ]


def test_handles_http_not_https():
    abstract = "old style at http://github.com/legacy/repo here"
    assert extract_code_urls(abstract) == ["http://github.com/legacy/repo"]


def test_handles_www_prefix():
    abstract = "see https://www.github.com/user/repo for details"
    assert extract_code_urls(abstract) == ["https://www.github.com/user/repo"]


def test_dedupes_repeated_urls():
    abstract = (
        "Code at https://github.com/x/y. We also reference https://github.com/x/y "
        "in section 3."
    )
    assert extract_code_urls(abstract) == ["https://github.com/x/y"]


def test_preserves_order_of_first_appearance():
    abstract = (
        "First: https://github.com/a/aa, then https://github.com/b/bb, "
        "then https://github.com/a/aa again."
    )
    assert extract_code_urls(abstract) == [
        "https://github.com/a/aa",
        "https://github.com/b/bb",
    ]


def test_no_match_returns_empty_list():
    abstract = "We propose a new method without published code."
    assert extract_code_urls(abstract) == []


def test_none_abstract_returns_empty_list():
    assert extract_code_urls(None) == []
    assert extract_code_urls("") == []


def test_ignores_non_code_hosts():
    abstract = "See https://arxiv.org/abs/1234.56789 and https://google.com/ for refs."
    assert extract_code_urls(abstract) == []


def test_strip_trailing_punctuation():
    assert _strip_trailing_punctuation("https://github.com/x/y.") == "https://github.com/x/y"
    assert _strip_trailing_punctuation("https://github.com/x/y),") == "https://github.com/x/y"
    assert _strip_trailing_punctuation("https://github.com/x/y") == "https://github.com/x/y"


# ────────────────────────────────────────────────────────────────────────────
# extract_candidates
# ────────────────────────────────────────────────────────────────────────────


def test_candidates_skips_papers_without_urls():
    discoveries = [
        {"id": "arxiv:1", "title": "no code", "abstract": "No code mentioned."},
        {
            "id": "arxiv:2",
            "title": "has code",
            "abstract": "Code: https://github.com/x/y",
            "url": "https://arxiv.org/abs/2",
            "source": "arxiv",
            "published": "2024-01-01",
        },
    ]
    candidates = extract_candidates(discoveries)
    assert len(candidates) == 1
    c = candidates[0]
    assert c["paper_id"] == "arxiv:2"
    assert c["title"] == "has code"
    assert c["code_urls"] == ["https://github.com/x/y"]
    assert c["url"] == "https://arxiv.org/abs/2"
    assert c["source"] == "arxiv"
    assert c["published"] == "2024-01-01"


def test_candidates_truncate_long_snippet():
    long_abs = "Lorem " * 100 + " https://github.com/x/y end."
    discoveries = [{"id": "arxiv:long", "abstract": long_abs}]
    candidates = extract_candidates(discoveries, snippet_chars=50)
    snippet = candidates[0]["abstract_snippet"]
    assert len(snippet) <= 51  # 50 chars + ellipsis
    assert snippet.endswith("…")


def test_candidates_short_snippet_no_ellipsis():
    discoveries = [{"id": "arxiv:short", "abstract": "Code: https://github.com/x/y"}]
    candidates = extract_candidates(discoveries, snippet_chars=240)
    assert not candidates[0]["abstract_snippet"].endswith("…")


def test_candidates_handles_missing_abstract():
    discoveries = [
        {"id": "arxiv:noab"},
        {"id": "arxiv:nullab", "abstract": None},
    ]
    assert extract_candidates(discoveries) == []


def test_candidates_handles_multiple_urls_per_paper():
    discoveries = [
        {
            "id": "arxiv:multi",
            "abstract": "Code at https://github.com/a/aa and data at https://github.com/b/bb.",
        }
    ]
    candidates = extract_candidates(discoveries)
    assert len(candidates) == 1
    assert candidates[0]["code_urls"] == [
        "https://github.com/a/aa",
        "https://github.com/b/bb",
    ]


# ────────────────────────────────────────────────────────────────────────────
# find_discovery_files / load_discoveries (filesystem)
# ────────────────────────────────────────────────────────────────────────────


def test_find_discovery_files_only_matches_pattern(tmp_path):
    # Pattern match
    (tmp_path / "discoveries_20260101.json").write_text("{}")
    (tmp_path / "discoveries_20260518.json").write_text("{}")
    # Should be ignored
    (tmp_path / "code_links_20260518.json").write_text("{}")
    (tmp_path / "discoveries.txt").write_text("nope")

    files = find_discovery_files(tmp_path)
    names = [f.name for f in files]
    assert names == ["discoveries_20260101.json", "discoveries_20260518.json"]


def test_find_discovery_files_empty_dir(tmp_path):
    assert find_discovery_files(tmp_path) == []


def test_load_discoveries_returns_list(tmp_path):
    fp = tmp_path / "discoveries_20260518.json"
    fp.write_text(json.dumps({
        "generated_at": "2026-05-18T00:00:00Z",
        "discoveries": [{"id": "arxiv:1"}, {"id": "arxiv:2"}],
    }))
    assert load_discoveries(fp) == [{"id": "arxiv:1"}, {"id": "arxiv:2"}]


def test_load_discoveries_missing_key_returns_empty(tmp_path):
    fp = tmp_path / "discoveries_20260518.json"
    fp.write_text(json.dumps({"generated_at": "..."}))
    assert load_discoveries(fp) == []
