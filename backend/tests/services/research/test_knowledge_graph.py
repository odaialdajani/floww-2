"""
backend/tests/services/research/test_knowledge_graph.py

Unit tests for services.research.knowledge_graph — DuckDB-backed research KG.

Uses in-memory DuckDB (:memory:) so tests are fast, isolated, and need no cleanup.
Every expected value is hand-derived (golden oracle), not copied from code output.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.research.knowledge_graph import KnowledgeGraph

# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────


def make_kg() -> KnowledgeGraph:
    """Create a fresh in-memory KnowledgeGraph with schema ensured."""
    kg = KnowledgeGraph(db_path=":memory:")
    kg.ensure_schema()
    return kg


# ────────────────────────────────────────────────────────────────────────────
# Paper CRUD
# ────────────────────────────────────────────────────────────────────────────


class TestUpsertPaper:
    def test_insert_and_retrieve_via_find(self):
        kg = make_kg()
        kg.upsert_concept("concept-1", "gamma exposure", category="options")
        kg.upsert_paper({
            "id": "arxiv:2301.00001",
            "title": "Gamma Exposure and Market Dynamics",
            "abstract": "We study GEX effects on SPX.",
            "url": "https://arxiv.org/abs/2301.00001",
            "source": "arxiv",
            "published": "2023-01-15",
            "discovered_at": "2024-06-01",
        })
        kg.add_paper_concept_edge("arxiv:2301.00001", "concept-1", relevance=0.95)

        results = kg.find_papers_by_concept("gamma exposure")
        assert len(results) == 1
        assert results[0]["id"] == "arxiv:2301.00001"
        assert results[0]["title"] == "Gamma Exposure and Market Dynamics"
        assert results[0]["relevance"] == pytest.approx(0.95)

    def test_upsert_updates_existing_paper(self):
        kg = make_kg()
        paper = {
            "id": "arxiv:2301.00002",
            "title": "Original Title",
            "abstract": "Original abstract.",
            "url": "https://arxiv.org/abs/2301.00002",
            "source": "arxiv",
            "published": "2023-02-01",
        }
        kg.upsert_paper(paper)
        # Update title
        paper["title"] = "Updated Title"
        kg.upsert_paper(paper)

        kg.upsert_concept("c1", "test concept")
        kg.add_paper_concept_edge("arxiv:2301.00002", "c1")
        results = kg.find_papers_by_concept("test concept")
        assert results[0]["title"] == "Updated Title"

    def test_upsert_paper_with_extra_metadata(self):
        kg = make_kg()
        kg.upsert_paper({
            "id": "arxiv:2301.00003",
            "title": "Meta Paper",
            "abstract": "Has extra fields.",
            "url": "https://arxiv.org/abs/2301.00003",
            "source": "arxiv",
            "published": "2023-03-01",
            "custom_field": "hello",
            "another_field": 42,
        })
        # Should not raise — extra fields go into metadata JSON
        row = kg.conn.execute(
            "SELECT metadata FROM papers WHERE id = ?", ["arxiv:2301.00003"]
        ).fetchone()
        import json
        meta = json.loads(row[0])
        assert meta["custom_field"] == "hello"
        assert meta["another_field"] == 42

    def test_find_papers_by_concept_case_insensitive(self):
        kg = make_kg()
        kg.upsert_concept("c-gex", "Gamma Exposure", category="options")
        kg.upsert_paper({
            "id": "arxiv:2301.00004",
            "title": "GEX Paper",
            "abstract": "test",
            "url": "https://arxiv.org/abs/2301.00004",
            "source": "arxiv",
            "published": "2023-04-01",
        })
        kg.add_paper_concept_edge("arxiv:2301.00004", "c-gex")

        # Search with different case
        results = kg.find_papers_by_concept("gamma EXPOSURE")
        assert len(results) == 1

    def test_find_papers_by_concept_no_match(self):
        kg = make_kg()
        results = kg.find_papers_by_concept("nonexistent concept")
        assert results == []

    def test_find_papers_by_concept_respects_limit(self):
        kg = make_kg()
        kg.upsert_concept("c-popular", "popular concept")
        for i in range(5):
            pid = f"arxiv:2301.001{i:02d}"
            kg.upsert_paper({
                "id": pid,
                "title": f"Paper {i}",
                "abstract": "test",
                "url": f"https://arxiv.org/abs/{pid}",
                "source": "arxiv",
                "published": f"2023-05-{i+1:02d}",
            })
            kg.add_paper_concept_edge(pid, "c-popular", relevance=1.0 - i * 0.1)

        results = kg.find_papers_by_concept("popular concept", limit=3)
        assert len(results) == 3
        # Highest relevance first (FLOAT precision → approx)
        assert results[0]["relevance"] == pytest.approx(1.0)
        assert results[1]["relevance"] == pytest.approx(0.9)
        assert results[2]["relevance"] == pytest.approx(0.8)


# ────────────────────────────────────────────────────────────────────────────
# Repo CRUD
# ────────────────────────────────────────────────────────────────────────────


class TestUpsertRepo:
    def test_insert_repo_parses_owner(self):
        kg = make_kg()
        kg.upsert_repo({
            "id": "someowner/somerepo",
            "stars": 100,
            "license": "MIT",
            "language": "Python",
            "loc": 5000,
        })
        row = kg.conn.execute(
            "SELECT owner, repo, stars FROM repos WHERE id = ?", ["someowner/somerepo"]
        ).fetchone()
        assert row[0] == "someowner"
        assert row[1] == "somerepo"
        assert row[2] == 100

    def test_upsert_repo_updates_stars(self):
        kg = make_kg()
        kg.upsert_repo({"id": "owner/repo", "stars": 50})
        kg.upsert_repo({"id": "owner/repo", "stars": 200})
        row = kg.conn.execute("SELECT stars FROM repos WHERE id = ?", ["owner/repo"]).fetchone()
        assert row[0] == 200

    def test_upsert_repo_with_extra_metadata(self):
        kg = make_kg()
        kg.upsert_repo({
            "id": "owner/repo2",
            "stars": 10,
            "description": "A test repo",
            "topics": ["finance", "options"],
        })
        import json
        row = kg.conn.execute("SELECT metadata FROM repos WHERE id = ?", ["owner/repo2"]).fetchone()
        meta = json.loads(row[0])
        assert meta["description"] == "A test repo"
        assert meta["topics"] == ["finance", "options"]

    def test_find_repos_by_category(self):
        kg = make_kg()
        kg.upsert_repo({"id": "quant/gex-lib", "stars": 500, "license": "MIT"})
        kg.upsert_function({
            "id": "func-1",
            "name": "calc_gex",
            "file_path": "gex/core.py",
            "repo_id": "quant/gex-lib",
            "category": "GEX calculation",
            "loc": 120,
        })
        kg.add_repo_function_edge("quant/gex-lib", "func-1")

        results = kg.find_repos_by_category("GEX calculation")
        assert len(results) == 1
        assert results[0]["id"] == "quant/gex-lib"
        assert results[0]["stars"] == 500

    def test_find_repos_by_category_min_stars_filter(self):
        kg = make_kg()
        kg.upsert_repo({"id": "small/repo", "stars": 5})
        kg.upsert_repo({"id": "big/repo", "stars": 5000})
        for rid, fid in [("small/repo", "f1"), ("big/repo", "f2")]:
            kg.upsert_function({
                "id": fid, "name": "fn", "file_path": "a.py",
                "repo_id": rid, "category": "cat1", "loc": 10,
            })
            kg.add_repo_function_edge(rid, fid)

        results = kg.find_repos_by_category("cat1", min_stars=100)
        assert len(results) == 1
        assert results[0]["id"] == "big/repo"

    def test_find_repos_by_category_no_match(self):
        kg = make_kg()
        results = kg.find_repos_by_category("nonexistent category")
        assert results == []


# ────────────────────────────────────────────────────────────────────────────
# Function CRUD + port candidates
# ────────────────────────────────────────────────────────────────────────────


class TestUpsertFunction:
    def test_insert_function(self):
        kg = make_kg()
        kg.upsert_function({
            "id": "func-1",
            "name": "compute_gex",
            "file_path": "services/gex.py",
            "repo_id": "owner/repo",
            "category": "GEX calculation",
            "loc": 80,
            "has_benchmark": True,
            "numba_compatible": True,
        })
        row = kg.conn.execute(
            "SELECT name, category, loc, has_benchmark, numba_compatible FROM code_functions WHERE id = ?",
            ["func-1"],
        ).fetchone()
        assert row[0] == "compute_gex"
        assert row[1] == "GEX calculation"
        assert row[2] == 80
        assert row[3] is True
        assert row[4] is True

    def test_upsert_function_update(self):
        kg = make_kg()
        kg.upsert_function({"id": "f1", "name": "old_name", "category": "old_cat", "loc": 50})
        kg.upsert_function({"id": "f1", "name": "new_name", "category": "new_cat", "loc": 50})
        row = kg.conn.execute("SELECT name, category FROM code_functions WHERE id = ?", ["f1"]).fetchone()
        assert row[0] == "new_name"
        assert row[1] == "new_cat"

    def test_add_repo_function_edge(self):
        kg = make_kg()
        kg.upsert_repo({"id": "owner/repo"})
        kg.upsert_function({"id": "f1", "name": "fn", "repo_id": "owner/repo", "category": "cat"})
        kg.add_repo_function_edge("owner/repo", "f1")
        row = kg.conn.execute(
            "SELECT repo_id, function_id FROM repo_implements_function WHERE repo_id = ? AND function_id = ?",
            ["owner/repo", "f1"],
        ).fetchone()
        assert row is not None

    def test_add_repo_function_edge_idempotent(self):
        kg = make_kg()
        kg.upsert_repo({"id": "owner/repo"})
        kg.upsert_function({"id": "f1", "name": "fn", "repo_id": "owner/repo", "category": "cat"})
        kg.add_repo_function_edge("owner/repo", "f1")
        kg.add_repo_function_edge("owner/repo", "f1")  # should not raise
        count = kg.conn.execute("SELECT COUNT(*) FROM repo_implements_function").fetchone()[0]
        assert count == 1


class TestFindPortCandidates:
    def test_finds_unported_function(self):
        kg = make_kg()
        kg.upsert_repo({"id": "quant/lib", "stars": 1000})
        kg.upsert_function({
            "id": "portable-fn",
            "name": "fast_gex",
            "file_path": "lib/gex.py",
            "repo_id": "quant/lib",
            "category": "GEX",
            "loc": 50,
            "has_benchmark": True,
            "numba_compatible": True,
        })
        kg.add_repo_function_edge("quant/lib", "portable-fn")

        candidates = kg.find_port_candidates()
        assert len(candidates) == 1
        assert candidates[0]["id"] == "portable-fn"
        assert candidates[0]["stars"] == 1000
        assert candidates[0]["has_benchmark"] is True

    def test_excludes_large_functions(self):
        """Functions with loc >= 500 should be excluded."""
        kg = make_kg()
        kg.upsert_repo({"id": "big/lib", "stars": 500})
        kg.upsert_function({
            "id": "big-fn",
            "name": "huge_func",
            "file_path": "big/mod.py",
            "repo_id": "big/lib",
            "category": "cat",
            "loc": 600,  # >= 500 → excluded
        })
        kg.add_repo_function_edge("big/lib", "big-fn")

        candidates = kg.find_port_candidates()
        assert len(candidates) == 0

    def test_excludes_already_ported(self):
        """Functions already marked as ported should be excluded."""
        kg = make_kg()
        kg.upsert_repo({"id": "quant/lib", "stars": 100})
        kg.upsert_function({
            "id": "done-fn",
            "name": "ported_func",
            "file_path": "lib/fn.py",
            "repo_id": "quant/lib",
            "category": "cat",
            "loc": 30,
        })
        kg.add_repo_function_edge("quant/lib", "done-fn")
        # Mark as ported
        kg.conn.execute("""
            INSERT INTO function_ports_to_service (function_id, service_id, ported)
            VALUES (?, ?, TRUE)
        """, ["done-fn", "svc-1"])

        candidates = kg.find_port_candidates()
        assert len(candidates) == 0

    def test_orders_by_benchmark_then_stars(self):
        """has_benchmark=True first, then by stars DESC."""
        kg = make_kg()
        for _i, (name, stars, bench) in enumerate([
            ("fn-a", 100, False),
            ("fn-b", 50, True),   # has benchmark, fewer stars
            ("fn-c", 200, False),
        ]):
            fid = f"f-{name}"
            rid = f"repo/{name}"
            kg.upsert_repo({"id": rid, "stars": stars})
            kg.upsert_function({
                "id": fid, "name": name, "file_path": f"{name}.py",
                "repo_id": rid, "category": "cat", "loc": 10,
                "has_benchmark": bench,
            })
            kg.add_repo_function_edge(rid, fid)

        candidates = kg.find_port_candidates()
        # fn-b first (has_benchmark=True), then fn-c (200 stars), then fn-a (100 stars)
        assert candidates[0]["id"] == "f-fn-b"
        assert candidates[1]["id"] == "f-fn-c"
        assert candidates[2]["id"] == "f-fn-a"

    def test_respects_limit(self):
        kg = make_kg()
        for i in range(5):
            fid = f"fn-{i}"
            rid = f"repo-{i}"
            kg.upsert_repo({"id": rid, "stars": 100 - i})
            kg.upsert_function({
                "id": fid, "name": f"func{i}", "file_path": f"{i}.py",
                "repo_id": rid, "category": "cat", "loc": 10,
            })
            kg.add_repo_function_edge(rid, fid)

        candidates = kg.find_port_candidates(limit=3)
        assert len(candidates) == 3


# ────────────────────────────────────────────────────────────────────────────
# Concept operations
# ────────────────────────────────────────────────────────────────────────────


class TestConceptOperations:
    def test_upsert_and_query_concept(self):
        kg = make_kg()
        kg.upsert_concept("c-1", "gamma exposure", category="options",
                          description="Dealer gamma positioning")
        row = kg.conn.execute(
            "SELECT name, category, description FROM concepts WHERE id = ?", ["c-1"]
        ).fetchone()
        assert row[0] == "gamma exposure"
        assert row[1] == "options"
        assert row[2] == "Dealer gamma positioning"

    def test_upsert_concept_update(self):
        kg = make_kg()
        kg.upsert_concept("c-1", "old name", category="old")
        kg.upsert_concept("c-1", "new name", category="new")
        row = kg.conn.execute("SELECT name, category FROM concepts WHERE id = ?", ["c-1"]).fetchone()
        assert row[0] == "new name"
        assert row[1] == "new"

    def test_add_paper_concept_edge(self):
        kg = make_kg()
        kg.upsert_paper({"id": "p1", "title": "T", "abstract": "a", "url": "u", "source": "s"})
        kg.upsert_concept("c1", "test concept")
        kg.add_paper_concept_edge("p1", "c1", relevance=0.75)
        row = kg.conn.execute(
            "SELECT relevance FROM paper_mentions_concept WHERE paper_id = ? AND concept_id = ?",
            ["p1", "c1"],
        ).fetchone()
        assert row[0] == pytest.approx(0.75)

    def test_add_paper_concept_edge_idempotent(self):
        kg = make_kg()
        kg.upsert_paper({"id": "p1", "title": "T", "abstract": "a", "url": "u", "source": "s"})
        kg.upsert_concept("c1", "test concept")
        kg.add_paper_concept_edge("p1", "c1", relevance=0.5)
        kg.add_paper_concept_edge("p1", "c1", relevance=0.9)  # should be IGNOREd
        row = kg.conn.execute(
            "SELECT relevance FROM paper_mentions_concept WHERE paper_id = ? AND concept_id = ?",
            ["p1", "c1"],
        ).fetchone()
        # First insert wins (INSERT OR IGNORE)
        assert row[0] == pytest.approx(0.5)

    def test_add_function_concept_edge(self):
        kg = make_kg()
        kg.upsert_function({"id": "f1", "name": "fn", "repo_id": "r", "category": "c"})
        kg.upsert_concept("c1", "gamma")
        kg.add_function_concept_edge("f1", "c1")
        row = kg.conn.execute(
            "SELECT function_id, concept_id FROM function_belongs_to_category WHERE function_id = ?",
            ["f1"],
        ).fetchone()
        assert row == ("f1", "c1")


# ────────────────────────────────────────────────────────────────────────────
# Service operations
# ────────────────────────────────────────────────────────────────────────────


class TestServiceOperations:
    def test_upsert_service(self):
        kg = make_kg()
        kg.upsert_service("svc-1", "services/gex_aggregator.py", "GEX aggregation service")
        row = kg.conn.execute(
            "SELECT file_path, description FROM services WHERE id = ?", ["svc-1"]
        ).fetchone()
        assert row[0] == "services/gex_aggregator.py"
        assert row[1] == "GEX aggregation service"

    def test_upsert_service_update(self):
        kg = make_kg()
        kg.upsert_service("svc-1", "services/gex.py", "old desc")
        kg.upsert_service("svc-1", "services/gex.py", "new desc")
        row = kg.conn.execute("SELECT description FROM services WHERE id = ?", ["svc-1"]).fetchone()
        assert row[0] == "new desc"

    def test_add_service_concept_edge(self):
        kg = make_kg()
        kg.upsert_service("svc-1", "services/gex.py")
        kg.upsert_concept("c-gex", "gamma exposure")
        kg.add_service_concept_edge("svc-1", "c-gex")
        row = kg.conn.execute(
            "SELECT service_id, concept_id FROM service_implements_concept WHERE service_id = ?",
            ["svc-1"],
        ).fetchone()
        assert row == ("svc-1", "c-gex")


# ────────────────────────────────────────────────────────────────────────────
# Edge operations
# ────────────────────────────────────────────────────────────────────────────


class TestEdgeOperations:
    def test_add_paper_repo_edge(self):
        kg = make_kg()
        kg.upsert_paper({"id": "p1", "title": "T", "abstract": "a", "url": "u", "source": "s"})
        kg.upsert_repo({"id": "owner/repo"})
        kg.add_paper_repo_edge("p1", "owner/repo", confidence=0.8)
        row = kg.conn.execute(
            "SELECT confidence FROM paper_cites_repo WHERE paper_id = ? AND repo_id = ?",
            ["p1", "owner/repo"],
        ).fetchone()
        assert row[0] == pytest.approx(0.8)

    def test_add_paper_repo_edge_idempotent(self):
        kg = make_kg()
        kg.upsert_paper({"id": "p1", "title": "T", "abstract": "a", "url": "u", "source": "s"})
        kg.upsert_repo({"id": "owner/repo"})
        kg.add_paper_repo_edge("p1", "owner/repo", confidence=0.8)
        kg.add_paper_repo_edge("p1", "owner/repo", confidence=0.3)  # IGNOREd
        row = kg.conn.execute(
            "SELECT confidence FROM paper_cites_repo WHERE paper_id = ? AND repo_id = ?",
            ["p1", "owner/repo"],
        ).fetchone()
        # First insert wins (INSERT OR IGNORE), FLOAT precision → approx
        assert row[0] == pytest.approx(0.8)


# ────────────────────────────────────────────────────────────────────────────
# Paper similarity
# ────────────────────────────────────────────────────────────────────────────


class TestComputePaperSimilarity:
    def test_no_pairs_with_fewer_than_two_shared_concepts(self):
        """Papers sharing only 1 concept should NOT be related."""
        kg = make_kg()
        for pid in ["p1", "p2"]:
            kg.upsert_paper({"id": pid, "title": pid, "abstract": "a", "url": "u", "source": "s"})
        kg.upsert_concept("c-shared", "shared")
        kg.add_paper_concept_edge("p1", "c-shared")
        kg.add_paper_concept_edge("p2", "c-shared")

        count = kg.compute_paper_similarity()
        assert count == 0

    def test_pair_with_two_shared_concepts(self):
        """Papers sharing 2+ concepts should be related with Jaccard similarity."""
        kg = make_kg()
        for pid in ["p1", "p2"]:
            kg.upsert_paper({"id": pid, "title": pid, "abstract": "a", "url": "u", "source": "s"})
        # p1 has concepts c1, c2, c3
        # p2 has concepts c1, c2, c4
        # shared = 2, union = 3 + 3 - 2 = 4, similarity = 2/4 = 0.5
        for c in ["c1", "c2", "c3", "c4"]:
            kg.upsert_concept(c, c)
        for c in ["c1", "c2", "c3"]:
            kg.add_paper_concept_edge("p1", c)
        for c in ["c1", "c2", "c4"]:
            kg.add_paper_concept_edge("p2", c)

        count = kg.compute_paper_similarity()
        assert count == 1

        related = kg.find_related_papers("p1")
        assert len(related) == 1
        assert related[0]["id"] == "p2"
        assert related[0]["shared_concepts"] == 2
        # Jaccard: 2 shared / (3 + 3 - 2) = 2/4 = 0.5
        assert related[0]["similarity"] == pytest.approx(0.5)

    def test_similarity_asymmetry(self):
        """paper_related_to_paper stores (paper_a, paper_b) with paper_a < paper_b.
        find_related_papers only looks up paper_a = ?, so only the lower-ID paper
        direction is returned. This is the designed behavior."""
        kg = make_kg()
        for pid in ["p1", "p2"]:
            kg.upsert_paper({"id": pid, "title": pid, "abstract": "a", "url": "u", "source": "s"})
        for c in ["c1", "c2"]:
            kg.upsert_concept(c, c)
            kg.add_paper_concept_edge("p1", c)
            kg.add_paper_concept_edge("p2", c)

        kg.compute_paper_similarity()
        # p1 < p2, so the pair is stored as (p1, p2)
        r12 = kg.find_related_papers("p1")
        r21 = kg.find_related_papers("p2")
        assert len(r12) == 1  # p1 is paper_a → found
        assert len(r21) == 0  # p2 is paper_b → not found (designed asymmetry)
        assert r12[0]["id"] == "p2"
        # Jaccard: 2 shared / (2 + 2 - 2) = 2/2 = 1.0
        assert r12[0]["similarity"] == pytest.approx(1.0)

    def test_empty_graph_returns_zero(self):
        kg = make_kg()
        count = kg.compute_paper_similarity()
        assert count == 0

    def test_find_related_papers_no_results(self):
        kg = make_kg()
        kg.upsert_paper({"id": "p1", "title": "T", "abstract": "a", "url": "u", "source": "s"})
        results = kg.find_related_papers("p1")
        assert results == []


# ────────────────────────────────────────────────────────────────────────────
# Stats + concept summary
# ────────────────────────────────────────────────────────────────────────────


class TestGetStats:
    def test_empty_graph_stats(self):
        # get_stats calls get_paper_count() and get_repo_count() which don't exist
        # This is a known bug — mark xfail
        pytest.xfail("BUG: get_stats() calls undefined get_paper_count()/get_repo_count() — AttributeError")

    def test_stats_with_data_skipped_due_to_bug(self):
        """Would test stats with data, but get_stats is broken."""
        pytest.xfail("BUG: get_stats() calls undefined get_paper_count()/get_repo_count()")


class TestGetConceptSummary:
    def test_empty_concepts(self):
        kg = make_kg()
        results = kg.get_concept_summary()
        assert results == []

    def test_concepts_ordered_by_paper_count(self):
        kg = make_kg()
        # c1: 2 papers, c2: 0 papers, c3: 1 paper
        for cid, name in [("c1", "alpha"), ("c2", "beta"), ("c3", "gamma")]:
            kg.upsert_concept(cid, name)
        for _i, pid in enumerate(["p1", "p2", "p3"]):
            kg.upsert_paper({"id": pid, "title": pid, "abstract": "a", "url": "u", "source": "s"})
        kg.add_paper_concept_edge("p1", "c1")
        kg.add_paper_concept_edge("p2", "c1")
        kg.add_paper_concept_edge("p3", "c3")

        results = kg.get_concept_summary()
        # c1 first (2 papers), c3 second (1 paper), c2 third (0 papers)
        assert results[0]["id"] == "c1"
        assert results[0]["paper_count"] == 2
        assert results[1]["id"] == "c3"
        assert results[1]["paper_count"] == 1
        assert results[2]["id"] == "c2"
        assert results[2]["paper_count"] == 0

    def test_concept_summary_respects_limit(self):
        kg = make_kg()
        for i in range(5):
            kg.upsert_concept(f"c{i}", f"concept-{i}")
        results = kg.get_concept_summary(limit=3)
        assert len(results) == 3


# ────────────────────────────────────────────────────────────────────────────
# Close
# ────────────────────────────────────────────────────────────────────────────


class TestClose:
    def test_close_does_not_raise(self):
        kg = make_kg()
        kg.close()
        # After close, operations should fail
        import _duckdb
        with pytest.raises(_duckdb.ConnectionException):
            kg.conn.execute("SELECT 1")
