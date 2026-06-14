# FINDINGS — Round 11, Agent 06 (knowledge_graph)

**Service:** `services/research/knowledge_graph.py`
**Branch:** `round11/agent-06-kgraph`
**Test file:** `tests/services/research/test_knowledge_graph.py`

## Coverage

| Class / Area | Tests |
|---|---|
| TestUpsertPaper | 6 tests — insert+retrieve, update, extra metadata, case-insensitive search, no-match, limit |
| TestUpsertRepo | 6 tests — owner parsing, star update, extra metadata, find by category, min_stars filter, no-match |
| TestUpsertFunction | 4 tests — insert, update, repo-function edge, idempotent edge |
| TestFindPortCandidates | 5 tests — finds unported, excludes large (loc>=500), excludes already-ported, ordering, limit |
| TestConceptOperations | 5 tests — upsert+query, update, paper-concept edge, idempotent edge, function-concept edge |
| TestServiceOperations | 3 tests — upsert, update, service-concept edge |
| TestEdgeOperations | 2 tests — paper-repo edge, idempotent |
| TestComputePaperSimilarity | 5 tests — <2 shared concepts, 2+ shared concepts, asymmetry, empty graph, no results |
| TestGetStats | 2 tests — both xfail (see BUG below) |
| TestGetConceptSummary | 3 tests — empty, ordered by paper count, limit |
| TestClose | 1 test — close + verify connection exception |

**Total: 42 tests (40 passed, 2 xfailed)**

## Bugs Found

### BUG-1: `get_stats()` calls undefined methods `get_paper_count()` / `get_repo_count()`

- **File:** `services/research/knowledge_graph.py`
- **Line:** 417-428 (`get_stats` method)
- **Issue:** `get_stats()` calls `self.get_paper_count()` and `self.get_repo_count()`, but these methods are **never defined** in the `KnowledgeGraph` class. Calling `get_stats()` raises `AttributeError`.
- **Expected:** Either define `get_paper_count()` and `get_repo_count()` methods, or inline the COUNT queries like the other stats do.
- **Fix suggestion:**
  ```python
  def get_stats(self) -> dict[str, int]:
      return {
          "papers": self.conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0],
          "repos": self.conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0],
          ...
      }
  ```
- **Tests:** 2 xfail tests document this bug (`TestGetStats::test_empty_graph_stats`, `TestGetStats::test_stats_with_data_skipped_due_to_bug`)

## Notes

- All tests use in-memory DuckDB (`:memory:`) for speed and isolation.
- All expected values are hand-derived (golden oracle), not copied from code output.
- DuckDB FLOAT is 32-bit, so float comparisons use `pytest.approx()`.
- `paper_related_to_paper` stores pairs with `paper_a < paper_b` (lexicographic), so `find_related_papers()` only returns results for the lower-ID paper. This is the designed behavior, not a bug.
