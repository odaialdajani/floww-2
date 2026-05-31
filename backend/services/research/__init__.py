"""Research-discovery services.

Finds open-source datasets, research papers, and code repositories relevant
to options trading / quant ML. Outputs go to `data/external_research/` for
human review before ingestion into the project's training pipeline.

Design (see `docs/adr/0003-research-discovery.md` when written):
- Each Source class wraps one external service (arxiv, HuggingFace, GitHub).
- Search → normalize to common schema → write JSON manifest.
- Nothing is auto-ingested. Discoveries are vetted manually or by a separate
  ingestion pass (TBD) before any datum touches Mongo or model training.
"""

from services.research.discovery import (
    ArxivSource,
    Discovery,
    DiscoverySource,
    discover_all,
)

__all__ = [
    "Discovery",
    "DiscoverySource",
    "ArxivSource",
    "discover_all",
]
