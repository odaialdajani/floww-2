#!/usr/bin/env python3
"""
backend/tests/services/memory/test_chart_embeddings.py — Tests for chart screenshot embeddings.

Run: pytest backend/tests/services/memory/test_chart_embeddings.py -v
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

# Mock PIL and clip before importing chart_embeddings (heavy deps not in venv)
# Suite-hygiene (2026-09-06): an earlier revision of this file injected the
# mocks into sys.modules and never restored them, silently breaking every
# later test that imports real PIL (e.g. heatmap PNG rendering). Import the
# REAL modules first (evicting any stale poison), then mock, import the
# service (which binds the mocks into its own namespace), then RESTORE the
# real modules so the rest of the suite is unaffected.
import importlib
import types

for _mod in ("PIL.Image", "PIL"):
    sys.modules.pop(_mod, None)
_real_pil = importlib.import_module("PIL")
_real_pil_image = importlib.import_module("PIL.Image")

_mock_pil = types.ModuleType("PIL")
_mock_pil_image = types.ModuleType("PIL.Image")
_mock_pil_image.open = MagicMock()
_mock_pil.Image = _mock_pil_image
sys.modules["PIL"] = _mock_pil
sys.modules["PIL.Image"] = _mock_pil_image

_mock_clip = types.ModuleType("clip")
_mock_clip.load = MagicMock(return_value=(MagicMock(), MagicMock()))
_mock_clip.tokenize = MagicMock(return_value=MagicMock())
sys.modules["clip"] = _mock_clip

from services.memory.chart_embeddings import (
    ChartEmbeddingIndex,
    get_chart_index,
    index_screenshots,
    search_screenshots,
)

# Restore real PIL for the remainder of the suite. chart_embeddings keeps
# its mock bindings (resolved at its import above); everyone else gets truth.
sys.modules["PIL"] = _real_pil
sys.modules["PIL.Image"] = _real_pil_image

# ---------------------------------------------------------------------------
# ChartEmbeddingIndex — pure logic (mocked CLIP)
# ---------------------------------------------------------------------------

class TestChartEmbeddingIndex:
    def _make_index(self):
        idx = ChartEmbeddingIndex.__new__(ChartEmbeddingIndex)
        idx.model_name = "ViT-B/32"
        idx._model = None
        idx._preprocess = None
        idx._embeddings = None
        idx._metadata = []
        return idx

    def _mock_model(self, arr):
        """Create a mock model whose encode_text returns a fake torch tensor
        that supports .cpu().numpy().flatten() -> arr."""
        mock_model = MagicMock()
        tensor = MagicMock()
        tensor.cpu.return_value = tensor
        tensor.numpy.return_value = arr
        tensor.flatten.return_value = arr.flatten()
        mock_model.encode_text.return_value = tensor
        return mock_model

    # -- load_index ---------------------------------------------------------

    def test_load_index_missing_cache(self, tmp_path):
        idx = self._make_index()
        with patch("services.memory.chart_embeddings.EMBEDDINGS_CACHE", tmp_path / "no.npz"), \
             patch("services.memory.chart_embeddings.EMBEDDINGS_META", tmp_path / "no.json"):
            assert idx.load_index() is False

    def test_load_index_present(self, tmp_path):
        idx = self._make_index()
        cache = tmp_path / "chart.npz"
        meta = tmp_path / "chart_meta.json"
        np.savez_compressed(cache, embeddings=np.eye(3))
        meta.write_text('[{"file": "/a.png", "filename": "a.png", "timestamp": 1.0, "size_bytes": 100}]')
        with patch("services.memory.chart_embeddings.EMBEDDINGS_CACHE", cache), \
             patch("services.memory.chart_embeddings.EMBEDDINGS_META", meta):
            assert idx.load_index() is True
            assert idx._embeddings.shape == (3, 3)

    # -- search (with pre-set embeddings) -----------------------------------

    def test_search_returns_results(self):
        idx = self._make_index()
        idx._embeddings = np.array([
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ])
        idx._metadata = [
            {"file": "/charts/a.png", "filename": "a.png"},
            {"file": "/charts/b.png", "filename": "b.png"},
            {"file": "/charts/c.png", "filename": "c.png"},
        ]
        idx._model = self._mock_model(np.array([[1.0, 0.0, 0.0]]))

        results = idx.search("a chart", top_k=2)
        assert len(results) == 2
        # First result should be a.png (highest cosine similarity to [1,0,0])
        assert results[0]["filename"] == "a.png"
        assert results[0]["score"] >= results[1]["score"]

    def test_search_result_structure(self):
        idx = self._make_index()
        idx._embeddings = np.array([[0.5, 0.5]])
        idx._metadata = [
            {"file": "/x/plot.png", "filename": "plot.png"},
        ]
        idx._model = self._mock_model(np.array([[0.5, 0.5]]))

        results = idx.search("test query")
        assert len(results) == 1
        r = results[0]
        assert "file" in r
        assert "filename" in r
        assert "score" in r
        assert r["filename"] == "plot.png"

    def test_search_top_k_limits(self):
        idx = self._make_index()
        idx._embeddings = np.eye(5)
        idx._metadata = [
            {"file": f"/c/{i}.png", "filename": f"{i}.png"} for i in range(5)
        ]
        idx._model = self._mock_model(np.array([[1.0, 0, 0, 0, 0]]))

        results = idx.search("q", top_k=3)
        assert len(results) == 3

    def test_search_empty_when_no_index(self):
        idx = self._make_index()
        idx._embeddings = None
        with patch.object(idx, "load_index", return_value=False):
            results = idx.search("anything")
            assert results == []

    def test_search_scores_are_floats(self):
        idx = self._make_index()
        idx._embeddings = np.array([[1.0, 0.0], [0.0, 1.0]])
        idx._metadata = [
            {"file": "/a.png", "filename": "a.png"},
            {"file": "/b.png", "filename": "b.png"},
        ]
        idx._model = self._mock_model(np.array([[0.7, 0.7]]))

        results = idx.search("q")
        for r in results:
            assert isinstance(r["score"], float)

    # -- cosine similarity edge cases ---------------------------------------

    def test_search_with_zero_norm_embedding(self):
        """Zero-norm embeddings should not cause division by zero."""
        idx = self._make_index()
        idx._embeddings = np.array([[0.0, 0.0], [1.0, 0.0]])
        idx._metadata = [
            {"file": "/zero.png", "filename": "zero.png"},
            {"file": "/norm.png", "filename": "norm.png"},
        ]
        idx._model = self._mock_model(np.array([[1.0, 0.0]]))

        # Should not raise
        results = idx.search("q")
        assert len(results) == 2

    # -- index_screenshots (mocked CLIP) ------------------------------------

    def test_index_screenshots_dir_missing(self, tmp_path):
        idx = self._make_index()
        count = idx.index_screenshots(screenshots_dir=tmp_path / "nonexistent")
        assert count == 0

    def test_index_screenshots_no_images(self, tmp_path):
        idx = self._make_index()
        (tmp_path / "readme.txt").write_text("not an image")
        count = idx.index_screenshots(screenshots_dir=tmp_path)
        assert count == 0


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

class TestModuleFunctions:
    def test_get_chart_index_singleton(self):
        """get_chart_index should return the same instance on repeated calls."""
        from services.memory import chart_embeddings as mod
        mod._chart_index = None
        idx1 = get_chart_index()
        idx2 = get_chart_index()
        assert idx1 is idx2
        mod._chart_index = None  # cleanup

    def test_search_screenshots_delegates(self):
        with patch("services.memory.chart_embeddings.get_chart_index") as mock_get:
            mock_idx = MagicMock()
            mock_idx.search.return_value = [{"file": "/a.png", "filename": "a.png", "score": 0.9}]
            mock_get.return_value = mock_idx
            results = search_screenshots("bullish chart", top_k=3)
            mock_idx.search.assert_called_once_with("bullish chart", 3)
            assert len(results) == 1

    def test_index_screenshots_delegates(self):
        with patch("services.memory.chart_embeddings.get_chart_index") as mock_get:
            mock_idx = MagicMock()
            mock_idx.index_screenshots.return_value = 7
            mock_get.return_value = mock_idx
            count = index_screenshots()
            mock_idx.index_screenshots.assert_called_once()
            assert count == 7


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
