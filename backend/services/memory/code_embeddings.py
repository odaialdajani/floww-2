#!/usr/bin/env python3
"""
backend/services/memory/code_embeddings.py — Code search via embeddings.

Embeds Python/TS/JS files using sentence-transformers (CodeBERT or MiniLM fallback).
Chunks per top-level def/class + module docstring.
Stored in a local numpy index for fast cosine similarity search.
"""

import ast
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Model selection: prefer CodeBERT, fall back to MiniLM
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"  # ~90MB, fast. Use "microsoft/codebert-base" for better code understanding (~500MB)

# Directories to index
CODE_DIRS = ["backend", "frontend/src", "scripts", "qc"]
REPO_ROOT = Path(__file__).resolve().resolve().parent.parent.parent.parent

# Cache file for embeddings
EMBEDDINGS_CACHE = Path.home() / ".hermes" / "code_embeddings.npz"
EMBEDDINGS_META = Path.home() / ".hermes" / "code_embeddings_meta.json"


class CodeChunk:
    """A chunk of code (function, class, or module docstring)."""

    def __init__(self, file_path: str, line_start: int, line_end: int,
                 chunk_type: str, name: str, text: str):
        self.file_path = file_path
        self.line_start = line_start
        self.line_end = line_end
        self.chunk_type = chunk_type
        self.name = name
        self.text = text

    @property
    def id(self) -> str:
        raw = f"{self.file_path}:{self.line_start}:{self.name}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {
            "file": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "type": self.chunk_type,
            "name": self.name,
            "text": self.text[:500],
        }


def extract_python_chunks(file_path: Path) -> list[CodeChunk]:
    """Extract code chunks from a Python file."""
    chunks = []
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = source.splitlines()

        # Module docstring
        if lines and (lines[0].strip().startswith('"""') or lines[0].strip().startswith("'''")):
            docstring_lines = []
            _in_doc = True
            for line in lines[:20]:  # First 20 lines max
                docstring_lines.append(line)
                if line.strip().endswith('"""') or line.strip().endswith("'''"):
                    _in_doc = False
                    break
            if docstring_lines:
                chunks.append(CodeChunk(
                    file_path=str(file_path),
                    line_start=1,
                    line_end=len(docstring_lines),
                    chunk_type="module_doc",
                    name=file_path.stem,
                    text="\n".join(docstring_lines),
                ))

        # AST-based extraction
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    start = node.lineno
                    end = node.end_lineno or start + 10
                    chunk_text = "\n".join(lines[start - 1:end])
                    chunks.append(CodeChunk(
                        file_path=str(file_path),
                        line_start=start,
                        line_end=end,
                        chunk_type="class" if isinstance(node, ast.ClassDef) else "function",
                        name=node.name,
                        text=chunk_text[:1000],  # Truncate long functions
                    ))
        except SyntaxError:
            pass

    except Exception as e:
        logger.warning(f"Failed to parse {file_path}: {e}")

    return chunks


def extract_js_chunks(file_path: Path) -> list[CodeChunk]:
    """Extract code chunks from JS/TS files (regex-based)."""
    chunks = []
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = source.splitlines()

        # Match function/class declarations
        func_pattern = re.compile(r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(')
        class_pattern = re.compile(r'^(?:export\s+)?class\s+(\w+)\s*(?:extends\s+\w+)?\s*\{')
        _method_pattern = re.compile(r'^\s+(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{')

        for i, line in enumerate(lines, 1):
            for pattern, chunk_type in [(func_pattern, "function"), (class_pattern, "class")]:
                m = pattern.match(line)
                if m:
                    # Extract until closing brace (simplified)
                    end = min(i + 50, len(lines))
                    chunk_text = "\n".join(lines[i - 1:end])
                    chunks.append(CodeChunk(
                        file_path=str(file_path),
                        line_start=i,
                        line_end=end,
                        chunk_type=chunk_type,
                        name=m.group(1),
                        text=chunk_text[:1000],
                    ))
                    break

    except Exception as e:
        logger.warning(f"Failed to parse {file_path}: {e}")

    return chunks



class CodeEmbeddingIndex:
    """Local code embedding index using sentence-transformers."""

    def __init__(self, model_name: str = EMBED_MODEL_NAME):
        self.model_name = model_name
        self._model = None
        self._embeddings = None
        self._metadata = []

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def build_index(self, repo_root: Path = REPO_ROOT) -> int:
        """Build embedding index for all code files. Returns number of chunks indexed."""
        all_chunks = []
        for dir_name in CODE_DIRS:
            dir_path = repo_root / dir_name
            if not dir_path.exists():
                continue
            for file_path in dir_path.rglob("*"):
                if file_path.suffix == ".py":
                    all_chunks.extend(extract_python_chunks(file_path))
                elif file_path.suffix in (".js", ".ts", ".tsx", ".jsx"):
                    all_chunks.extend(extract_js_chunks(file_path))
        if not all_chunks:
            logger.warning("No code chunks found")
            return 0
        texts = [c.text for c in all_chunks]
        logger.info(f"Embedding {len(texts)} code chunks...")
        embeddings = self.model.encode(texts, show_progress_bar=False)
        EMBEDDINGS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(EMBEDDINGS_CACHE, embeddings=embeddings)
        EMBEDDINGS_META.write_text(json.dumps([c.to_dict() for c in all_chunks]))
        self._embeddings = embeddings
        self._metadata = [c.to_dict() for c in all_chunks]
        logger.info(f"Indexed {len(all_chunks)} code chunks from {len(CODE_DIRS)} directories")
        return len(all_chunks)

    def load_index(self) -> bool:
        """Load cached embeddings."""
        if not EMBEDDINGS_CACHE.exists() or not EMBEDDINGS_META.exists():
            return False
        data = np.load(str(EMBEDDINGS_CACHE))
        self._embeddings = data["embeddings"]
        self._metadata = json.loads(EMBEDDINGS_META.read_text())
        return True

    def search(self, query: str, top_k: int = 5) -> list:
        """Search code by semantic similarity."""
        if self._embeddings is None:
            if not self.load_index():
                return []
        query_embedding = self.model.encode([query])
        similarities = np.dot(self._embeddings, query_embedding.T).flatten()
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        results = []
        for idx in top_indices:
            meta = self._metadata[idx]
            results.append({
                "file": meta["file"],
                "line": meta["line_start"],
                "name": meta["name"],
                "type": meta["type"],
                "score": float(similarities[idx]),
                "snippet": meta["text"][:200],
            })
        return results


_code_index: Optional[CodeEmbeddingIndex] = None


def get_code_index() -> CodeEmbeddingIndex:
    global _code_index
    if _code_index is None:
        _code_index = CodeEmbeddingIndex()
    return _code_index


def search_code(query: str, top_k: int = 5) -> list[dict]:
    """Search code by semantic similarity. Returns list of {file, line, name, score, snippet}."""
    return get_code_index().search(query, top_k)


def build_code_index() -> int:
    """Build and cache code embeddings. Returns number of chunks indexed."""
    return get_code_index().build_index()
