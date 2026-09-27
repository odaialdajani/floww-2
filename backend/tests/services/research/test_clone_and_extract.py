"""Tests for ``scripts/clone_and_extract.py``.

Covers URL parsing, manifest awareness, plan construction, and queue I/O.
The actual ``git clone`` subprocess is not exercised in unit tests — see
``test_main_dry_run`` for the end-to-end dry-run path.
License and repository-size reads are mocked; every test runs offline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import clone_and_extract as ce  # noqa: E402


@pytest.fixture
def repository_checks(monkeypatch):
    license_check = Mock(return_value=(True, "MIT"))
    size_check = Mock(return_value=1.0)
    monkeypatch.setattr(ce, "check_license", license_check)
    monkeypatch.setattr(ce, "get_repo_size_mb", size_check)
    return license_check, size_check


# ---------------------------------------------------------------- parse_owner_repo
@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/owen8877/RLOP", ("owen8877", "RLOP")),
        ("https://github.com/asridi/DML-Calibration-Heston-Model", ("asridi", "DML-Calibration-Heston-Model")),
        ("http://github.com/foo/bar", ("foo", "bar")),
        ("https://www.github.com/foo/bar", ("foo", "bar")),
        ("https://github.com/foo/bar.git", ("foo", "bar")),
        ("https://github.com/foo/bar/", ("foo", "bar")),
        ("https://gitlab.com/foo/bar", ("foo", "bar")),
        ("https://bitbucket.org/foo/bar", ("foo", "bar")),
    ],
)
def test_parse_owner_repo_accepts(url, expected):
    assert ce.parse_owner_repo(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/foo/bar",  # not a code host
        "https://arxiv.org/abs/2309.07843",  # paper URL, not a repo
        "https://github.com/foo",  # missing repo
        "https://github.com/",  # nothing
        "garbage",
    ],
)
def test_parse_owner_repo_rejects(url):
    assert ce.parse_owner_repo(url) is None


# ---------------------------------------------------------------- local_dir_for
def test_local_dir_for_uses_underscore_convention():
    result = ce.local_dir_for("owen8877", "RLOP")
    assert result.name == "owen8877_RLOP"
    assert result.parent == ce.CLONED_DIR


# ---------------------------------------------------------------- load_cloned_manifest
def test_load_cloned_manifest_missing_file(tmp_path):
    result = ce.load_cloned_manifest(tmp_path / "nope.json")
    assert result == {"cloned": [], "count": 0}


def test_load_cloned_manifest_reads_existing(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"cloned": ["a/b"], "count": 1}))
    assert ce.load_cloned_manifest(p) == {"cloned": ["a/b"], "count": 1}


# ---------------------------------------------------------------- already_cloned
def test_already_cloned_via_manifest():
    manifest = {"cloned": ["owen8877/RLOP"], "count": 1}
    assert ce.already_cloned("owen8877", "RLOP", manifest) is True


def test_already_cloned_via_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "CLONED_DIR", tmp_path)
    (tmp_path / "owner_repo").mkdir()
    assert ce.already_cloned("owner", "repo", {"cloned": [], "count": 0}) is True


def test_already_cloned_false_when_neither(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "CLONED_DIR", tmp_path)
    assert ce.already_cloned("new", "repo", {"cloned": [], "count": 0}) is False


# ---------------------------------------------------------------- find_latest_code_links
def test_find_latest_code_links_picks_most_recent(tmp_path):
    (tmp_path / "code_links_20260101.json").write_text("{}")
    (tmp_path / "code_links_20260518.json").write_text("{}")
    (tmp_path / "code_links_20260301.json").write_text("{}")
    result = ce.find_latest_code_links(tmp_path)
    assert result.name == "code_links_20260518.json"


def test_find_latest_code_links_none_when_empty(tmp_path):
    assert ce.find_latest_code_links(tmp_path) is None


# ---------------------------------------------------------------- collect_candidates
def _sample_code_links_file(tmp_path):
    payload = {
        "candidates": [
            {
                "paper_id": "arxiv:1",
                "title": "Paper One",
                "url": "https://arxiv.org/abs/1",
                "code_urls": ["https://github.com/a/b", "https://github.com/c/d"],
            },
            {
                "paper_id": "arxiv:2",
                "title": "Paper Two",
                "url": "https://arxiv.org/abs/2",
                "code_urls": ["https://github.com/a/b"],  # duplicate URL, different paper
            },
        ]
    }
    p = tmp_path / "code_links.json"
    p.write_text(json.dumps(payload))
    return p


def test_collect_candidates_flattens_with_provenance(tmp_path):
    p = _sample_code_links_file(tmp_path)
    rows = ce.collect_candidates(p)
    assert len(rows) == 3
    assert {r["code_url"] for r in rows} == {"https://github.com/a/b", "https://github.com/c/d"}
    # provenance preserved
    assert rows[0]["paper_id"] == "arxiv:1"
    assert rows[2]["paper_id"] == "arxiv:2"


def test_collect_candidates_only_filter(tmp_path):
    p = _sample_code_links_file(tmp_path)
    rows = ce.collect_candidates(p, only=["https://github.com/c/d"])
    assert len(rows) == 1
    assert rows[0]["code_url"] == "https://github.com/c/d"


# ---------------------------------------------------------------- plan_clones
def test_plan_clones_buckets(tmp_path, monkeypatch, repository_checks):
    monkeypatch.setattr(ce, "CLONED_DIR", tmp_path)
    candidates = [
        {"paper_id": "p1", "paper_title": "T1", "paper_url": "u1", "code_url": "https://github.com/a/b"},
        {"paper_id": "p2", "paper_title": "T2", "paper_url": "u2", "code_url": "https://github.com/a/b"},  # dup
        {"paper_id": "p3", "paper_title": "T3", "paper_url": "u3", "code_url": "https://github.com/x/y"},
        {"paper_id": "p4", "paper_title": "T4", "paper_url": "u4", "code_url": "garbage"},
    ]
    manifest = {"cloned": ["a/b"], "count": 1}
    plan = ce.plan_clones(candidates, manifest)
    repository_checks[0].assert_called_once()
    assert repository_checks[0].call_args.args[:2] == ("x", "y")
    repository_checks[1].assert_called_once_with("x", "y")
    assert [c["code_url"] for c in plan["to_clone"]] == ["https://github.com/x/y"]
    assert [c["code_url"] for c in plan["skip_already"]] == ["https://github.com/a/b"]
    assert [c["code_url"] for c in plan["skip_unparseable"]] == ["garbage"]


# ---------------------------------------------------------------- update_manifest
def test_update_manifest_appends_new():
    result = ce.update_manifest({"cloned": ["a/b"], "count": 1}, "x", "y")
    assert result == {"cloned": ["a/b", "x/y"], "count": 2}


def test_update_manifest_idempotent():
    result = ce.update_manifest({"cloned": ["a/b"], "count": 1}, "a", "b")
    assert result == {"cloned": ["a/b"], "count": 1}


# ---------------------------------------------------------------- write_queue
def test_write_queue_payload_shape(tmp_path):
    plan = {"to_clone": [{"code_url": "https://github.com/a/b"}], "skip_already": [], "skip_unparseable": []}
    out = tmp_path / "q.json"
    ce.write_queue(plan, out)
    data = json.loads(out.read_text())
    assert set(data) == {"generated_at", "to_clone", "skip_already", "skip_unparseable",
                         "skip_license", "skip_size", "counts"}
    assert data["skip_license"] == data["skip_size"] == []
    assert data["counts"]["skip_license"] == data["counts"]["skip_size"] == 0
    assert data["counts"]["to_clone"] == 1


# ---------------------------------------------------------------- append_provenance
def test_append_provenance_creates_then_appends(tmp_path):
    path = tmp_path / "prov.json"
    ce.append_provenance([{"owner": "a", "repo": "b"}], path=path)
    ce.append_provenance([{"owner": "c", "repo": "d"}], path=path)
    data = json.loads(path.read_text())
    assert len(data) == 2
    assert [r["owner"] for r in data] == ["a", "c"]


# ---------------------------------------------------------------- main dry-run path
def test_main_dry_run_writes_queue_and_returns_zero(tmp_path, monkeypatch, repository_checks):
    # Isolate paths
    monkeypatch.setattr(ce, "GITHUB_REPOS_DIR", tmp_path)
    monkeypatch.setattr(ce, "CLONED_DIR", tmp_path / "cloned")
    monkeypatch.setattr(ce, "CLONED_MANIFEST", tmp_path / "cloned-manifest.json")

    data_dir = tmp_path / "ext"
    data_dir.mkdir()
    p = data_dir / "code_links_20260101.json"
    p.write_text(json.dumps({
        "candidates": [{
            "paper_id": "p1", "title": "T", "url": "u",
            "code_urls": ["https://github.com/a/b"],
        }]
    }))

    execute = Mock(side_effect=AssertionError("Dry run must not clone"))
    monkeypatch.setattr(ce, "execute_plan", execute)
    rc = ce.main(["--data-dir", str(data_dir)])
    execute.assert_not_called()
    repository_checks[0].assert_called_once()
    repository_checks[1].assert_called_once_with("a", "b")
    assert rc == 0
    queues = list(tmp_path.glob("clone_queue_*.json"))
    assert len(queues) == 1
    data = json.loads(queues[0].read_text())
    assert data["counts"]["to_clone"] == 1


def test_main_returns_2_when_no_code_links_file(tmp_path):
    rc = ce.main(["--data-dir", str(tmp_path)])
    assert rc == 2


def test_main_execute_without_yes_returns_3(tmp_path, monkeypatch, repository_checks):
    monkeypatch.setattr(ce, "GITHUB_REPOS_DIR", tmp_path)
    monkeypatch.setattr(ce, "CLONED_DIR", tmp_path / "cloned")
    monkeypatch.setattr(ce, "CLONED_MANIFEST", tmp_path / "cloned-manifest.json")

    data_dir = tmp_path / "ext"
    data_dir.mkdir()
    (data_dir / "code_links_20260101.json").write_text(json.dumps({
        "candidates": [{
            "paper_id": "p1", "title": "T", "url": "u",
            "code_urls": ["https://github.com/a/b"],
        }]
    }))

    execute = Mock(side_effect=AssertionError("Missing confirmation must not clone"))
    monkeypatch.setattr(ce, "execute_plan", execute)
    rc = ce.main(["--data-dir", str(data_dir), "--execute"])
    execute.assert_not_called()
    assert rc == 3
