#!/usr/bin/env python3
"""
backend/tests/services/memory/test_code_embeddings.py - Tests for code embedding search.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from services.memory.code_embeddings import (  # noqa: E402, I001
    CodeChunk,
    CodeEmbeddingIndex,
    extract_js_chunks,
    extract_python_chunks,
)


class TestCodeChunk:
    def test_create(self):
        c = CodeChunk("a.py", 10, 25, "function", "foo", "def foo():\n    pass")
        assert c.file_path == "a.py" and c.name == "foo" and c.chunk_type == "function"

    def test_id_deterministic(self):
        c1 = CodeChunk("a.py", 1, 5, "function", "x", "t")
        c2 = CodeChunk("a.py", 1, 5, "function", "x", "t")
        assert c1.id == c2.id

    def test_id_differs(self):
        c1 = CodeChunk("a.py", 1, 5, "function", "x", "t")
        c2 = CodeChunk("a.py", 1, 5, "function", "y", "t")
        assert c1.id != c2.id

    def test_to_dict(self):
        d = CodeChunk("b.py", 3, 10, "class", "C", "class C: ...").to_dict()
        assert d["file"] == "b.py" and d["type"] == "class" and d["name"] == "C"

    def test_to_dict_truncates(self):
        d = CodeChunk("f.py", 1, 2, "fn", "fn", "x" * 1000).to_dict()
        assert len(d["text"]) <= 500


class TestExtractPythonChunks:
    def _w(self, tmp_path, name, content):
        f = tmp_path / name
        f.write_text(content)
        return f

    def test_function(self, tmp_path):
        fp = self._w(tmp_path, "t.py", "def hello():\n    pass\n")
        funcs = [c for c in extract_python_chunks(fp) if c.chunk_type == "function"]
        assert len(funcs) == 1 and funcs[0].name == "hello"

    def test_class(self, tmp_path):
        fp = self._w(tmp_path, "t.py", "class Foo:\n    pass\n")
        cls = [c for c in extract_python_chunks(fp) if c.chunk_type == "class"]
        assert len(cls) == 1 and cls[0].name == "Foo"

    def test_docstring(self, tmp_path):
        fp = self._w(tmp_path, "t.py", '"""Doc."""\n')
        docs = [c for c in extract_python_chunks(fp) if c.chunk_type == "module_doc"]
        assert len(docs) == 1

    def test_empty(self, tmp_path):
        assert extract_python_chunks(self._w(tmp_path, "t.py", "")) == []

    def test_syntax_error(self, tmp_path):
        assert isinstance(extract_python_chunks(self._w(tmp_path, "t.py", "def b(\n")), list)

    def test_async(self, tmp_path):
        fp = self._w(tmp_path, "t.py", "async def f():\n    pass\n")
        funcs = [c for c in extract_python_chunks(fp) if c.chunk_type == "function"]
        assert len(funcs) == 1 and funcs[0].name == "f"

    def test_multiple(self, tmp_path):
        fp = self._w(tmp_path, "t.py", "def a():\n    pass\ndef b():\n    pass\n")
        funcs = [c for c in extract_python_chunks(fp) if c.chunk_type == "function"]
        assert len(funcs) == 2


class TestExtractJSChunks:
    def _w(self, tmp_path, name, content):
        f = tmp_path / name
        f.write_text(content)
        return f

    def test_function(self, tmp_path):
        fp = self._w(tmp_path, "t.js", "function g() {\n}\n")
        funcs = [c for c in extract_js_chunks(fp) if c.chunk_type == "function"]
        assert len(funcs) == 1 and funcs[0].name == "g"

    def test_class(self, tmp_path):
        fp = self._w(tmp_path, "t.js", "class W {\n}\n")
        cls = [c for c in extract_js_chunks(fp) if c.chunk_type == "class"]
        assert len(cls) == 1 and cls[0].name == "W"

    def test_export(self, tmp_path):
        fp = self._w(tmp_path, "t.js", "export function h() {\n}\n")
        funcs = [c for c in extract_js_chunks(fp) if c.chunk_type == "function"]
        assert len(funcs) == 1 and funcs[0].name == "h"

    def test_async(self, tmp_path):
        fp = self._w(tmp_path, "t.js", "async function l() {\n}\n")
        funcs = [c for c in extract_js_chunks(fp) if c.chunk_type == "function"]
        assert len(funcs) == 1 and funcs[0].name == "l"

    def test_empty(self, tmp_path):
        assert extract_js_chunks(self._w(tmp_path, "t.js", "")) == []


class TestCodeEmbeddingIndex:
    def _make(self):
        idx = CodeEmbeddingIndex.__new__(CodeEmbeddingIndex)
        idx.model_name = "test"
        idx._model = None
        idx._embeddings = None
        idx._metadata = []
        return idx

    def test_search_empty(self):
        idx = self._make()
        idx._embeddings = None
        with patch.object(idx, "load_index", return_value=False):
            idx._model = MagicMock()
            idx._model.encode.return_value = np.array([[1.0, 0.0]])
            assert idx.search("q") == []

    def test_search_results(self):
        idx = self._make()
        idx._embeddings = np.array([[1.0, 0.0], [0.0, 1.0]])
        idx._metadata = [
            {"file": "a.py", "line_start": 1, "name": "fa", "type": "function", "text": "t"},
            {"file": "b.py", "line_start": 10, "name": "fb", "type": "function", "text": "t"},
        ]
        m = MagicMock()
        m.encode.return_value = np.array([[1.0, 0.0]])
        idx._model = m
        r = idx.search("q", top_k=1)
        assert len(r) == 1 and r[0]["file"] == "a.py"

    def test_search_top_k(self):
        idx = self._make()
        idx._embeddings = np.eye(5)
        idx._metadata = [
            {"file": f"f{i}.py", "line_start": i, "name": f"fn{i}", "type": "function", "text": "t"}
            for i in range(5)
        ]
        m = MagicMock()
        m.encode.return_value = np.array([[1.0, 0, 0, 0, 0]])
        idx._model = m
        assert len(idx.search("q", top_k=3)) == 3

    def test_search_fields(self):
        idx = self._make()
        idx._embeddings = np.array([[0.5, 0.5]])
        idx._metadata = [
            {"file": "x.py", "line_start": 42, "name": "s", "type": "function", "text": "t"},
        ]
        m = MagicMock()
        m.encode.return_value = np.array([[0.5, 0.5]])
        idx._model = m
        r = idx.search("t")[0]
        for f in ("file", "line", "name", "type", "score", "snippet"):
            assert f in r


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
