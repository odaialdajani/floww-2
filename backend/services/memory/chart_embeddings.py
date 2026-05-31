#!/usr/bin/env python3
"""
backend/services/memory/chart_embeddings.py — Chart screenshot embeddings via CLIP.

Watches ~/Documents/floww-screenshots/ for new images.
Embeds via openai/clip-vit-base-patch32.
Stores in local numpy index for fast similarity search.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = Path.home() / "Documents" / "floww-screenshots"
EMBEDDINGS_CACHE = Path.home() / ".hermes" / "chart_embeddings.npz"
EMBEDDINGS_META = Path.home() / ".hermes" / "chart_embeddings_meta.json"

class ChartEmbeddingIndex:
    """CLIP-based chart screenshot embedding index."""

    def __init__(self, model_name: str = "ViT-B/32"):
        self.model_name = model_name
        self._model = None
        self._preprocess = None
        self._embeddings = None
        self._metadata = []

    @property
    def model(self):
        if self._model is None:
            import clip
            logger.info(f"Loading CLIP model: {self.model_name}")
            self._model, self._preprocess = clip.load(self.model_name, device="cpu")
        return self._model

    def _load_image(self, path: Path):
        """Load and preprocess an image for CLIP."""
        image = self._preprocess(Image.open(str(path))).unsqueeze(0)
        return image

    def embed_image(self, image_path: Path) -> np.ndarray:
        """Embed a single image."""
        import torch
        image = self._load_image(image_path)
        with torch.no_grad():
            features = self.model.encode_image(image)
        return features.cpu().numpy().flatten()

    def embed_text(self, text: str) -> np.ndarray:
        """Embed a text query."""
        import clip
        import torch
        tokens = clip.tokenize([text])
        with torch.no_grad():
            features = self.model.encode_text(tokens)
        return features.cpu().numpy().flatten()

    def index_screenshots(self, screenshots_dir: Path = SCREENSHOTS_DIR) -> int:
        """Index all screenshots in the watch directory."""
        if not screenshots_dir.exists():
            logger.info(f"Screenshots dir not found: {screenshots_dir}")
            return 0

        image_files = list(screenshots_dir.glob("*.png")) + \
                      list(screenshots_dir.glob("*.jpg")) + \
                      list(screenshots_dir.glob("*.jpeg"))

        if not image_files:
            logger.info("No screenshots found")
            return 0

        logger.info(f"Indexing {len(image_files)} screenshots...")
        embeddings = []
        metadata = []

        for img_path in image_files:
            try:
                emb = self.embed_image(img_path)
                embeddings.append(emb)
                stat = img_path.stat()
                metadata.append({
                    "file": str(img_path),
                    "filename": img_path.name,
                    "timestamp": stat.st_mtime,
                    "size_bytes": stat.st_size,
                })
            except Exception as e:
                logger.warning(f"Failed to embed {img_path}: {e}")

        if not embeddings:
            return 0

        embeddings_array = np.array(embeddings)
        EMBEDDINGS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(EMBEDDINGS_CACHE, embeddings=embeddings_array)
        EMBEDDINGS_META.write_text(json.dumps(metadata))

        self._embeddings = embeddings_array
        self._metadata = metadata

        logger.info(f"Indexed {len(metadata)} screenshots")
        return len(metadata)

    def load_index(self) -> bool:
        """Load cached embeddings."""
        if not EMBEDDINGS_CACHE.exists() or not EMBEDDINGS_META.exists():
            return False
        data = np.load(str(EMBEDDINGS_CACHE))
        self._embeddings = data["embeddings"]
        self._metadata = json.loads(EMBEDDINGS_META.read_text())
        return True

    def search(self, text_query: str, top_k: int = 5) -> list[dict]:
        """Search screenshots by text query."""
        if self._embeddings is None:
            if not self.load_index():
                return []

        query_emb = self.embed_text(text_query)
        # Cosine similarity
        norms = np.linalg.norm(self._embeddings, axis=1) * np.linalg.norm(query_emb)
        norms = np.where(norms == 0, 1e-8, norms)
        similarities = np.dot(self._embeddings, query_emb) / norms
        top_indices = np.argsort(similarities)[-top_k:][::-1]

        results = []
        for idx in top_indices:
            meta = self._metadata[idx]
            results.append({
                "file": meta["file"],
                "filename": meta["filename"],
                "score": float(similarities[idx]),
            })
        return results



_chart_index: Optional[ChartEmbeddingIndex] = None


def get_chart_index() -> ChartEmbeddingIndex:
    global _chart_index
    if _chart_index is None:
        _chart_index = ChartEmbeddingIndex()
    return _chart_index


def search_screenshots(text_query: str, top_k: int = 5) -> list[dict]:
    """Search screenshots by text query. Returns list of {file, filename, score}."""
    return get_chart_index().search(text_query, top_k)


def index_screenshots() -> int:
    """Index all screenshots. Returns count."""
    return get_chart_index().index_screenshots()
