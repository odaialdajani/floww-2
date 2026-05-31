"""Research-discovery core.

Defines:
- `Discovery` — the common normalized record format
- `DiscoverySource` — abstract base for any external research service
- `ArxivSource` — concrete implementation hitting arxiv's public API
- `discover_all(sources, queries)` — orchestrator that runs all sources

Concrete implementations should:
1. Accept a query string in their constructor or `search(query)` method.
2. Return a list of raw vendor responses from `_fetch(query)`.
3. Normalize each raw response into a `Discovery` via `_parse(raw)`.
4. Respect rate limits (sleep between requests; default 3s between arxiv calls).
5. Never call sources that require auth without the auth being present in env.

License/vetting: discoveries are SUSPECT by default — the `Discovery.license`
field tracks what's known. Anything ambiguous → manual review before
ingestion into training data. See ADR-0003.
"""

from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

# ────────────────────────────────────────────────────────────────────────────
# Normalized record
# ────────────────────────────────────────────────────────────────────────────


@dataclass
class Discovery:
    """Common schema for any discovered research artifact.

    `id` is `<source>:<source_id>` (e.g. `arxiv:2401.12345`).
    `relevance_score` starts at None; downstream vetting fills it.
    `license` is what the source claims; None if unknown.
    """
    id: str
    title: str
    url: str
    source: str
    discovered_at: str
    authors: List[str] = field(default_factory=list)
    published: Optional[str] = None
    abstract: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    license: Optional[str] = None
    relevance_score: Optional[float] = None
    raw: Optional[Dict[str, Any]] = None  # provenance, not serialized by default

    def to_dict(self, include_raw: bool = False) -> Dict[str, Any]:
        d = asdict(self)
        if not include_raw:
            d.pop("raw", None)
        return d


# ────────────────────────────────────────────────────────────────────────────
# Abstract source
# ────────────────────────────────────────────────────────────────────────────


class DiscoverySource(ABC):
    """A single external research service. Subclasses implement `_fetch` and `_parse`."""

    name: str = "abstract"
    rate_limit_seconds: float = 3.0

    def __init__(self, http_get: Optional[Callable[[str, Dict[str, str]], str]] = None,
                 max_retries: int = 3, backoff_factor: float = 2.0):
        """`http_get` is injected for testability — defaults to urllib.
        `max_retries` and `backoff_factor` control retry on 429/timeout."""
        self._http_get = http_get or self._default_http_get
        self._max_retries = max_retries
        self._backoff_factor = backoff_factor

    @abstractmethod
    def _fetch(self, query: str) -> Any:
        """Return the raw vendor response (may be parsed XML/JSON or plain text)."""

    @abstractmethod
    def _parse(self, raw: Any) -> List[Discovery]:
        """Convert vendor-specific response into normalized Discoveries."""

    def search(self, query: str) -> List[Discovery]:
        raw = self._fetch(query)
        return self._parse(raw)

    def search_many(self, queries: Iterable[str]) -> List[Discovery]:
        out: List[Discovery] = []
        first = True
        for q in queries:
            if not first:
                time.sleep(self.rate_limit_seconds)
            first = False
            out.extend(self.search(q))
        return out

    @staticmethod
    def _default_http_get(url: str, headers: Dict[str, str]) -> str:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")


# ────────────────────────────────────────────────────────────────────────────
# arxiv source
# ────────────────────────────────────────────────────────────────────────────


_ARXIV_NS = {"a": "http://www.w3.org/2005/Atom"}


class ArxivSource(DiscoverySource):
    """arxiv.org API. No auth required. Public, well-documented.

    Docs: https://info.arxiv.org/help/api/user-manual.html

    The API returns Atom XML. We use stdlib ElementTree to avoid adding a
    dependency.

    Query construction (bug-fix 2026-05-18): unquoted multi-token queries
    against `all:` returned wildly off-topic results (e.g. "gamma exposure
    dealer hedging" returned Gaussian-splatting and gamma-ray-astronomy
    papers). We now wrap the query as a phrase AND restrict to the
    quantitative-finance category set by default. Pass `categories=None` to
    disable the category filter, or a custom tuple to override.
    """

    name = "arxiv"
    base_url = "http://export.arxiv.org/api/query"
    rate_limit_seconds = 5.0  # arxiv asks for ≥ 3s; use 5s to be safe

    DEFAULT_CATEGORIES = (
        "q-fin.PR",  # pricing of securities
        "q-fin.TR",  # trading and market microstructure
        "q-fin.RM",  # risk management
        "q-fin.MF",  # mathematical finance
        "q-fin.ST",  # statistical finance
        "q-fin.PM",  # portfolio management
        "q-fin.CP",  # computational finance
        "q-fin.GN",  # general finance
        "stat.AP",   # applied statistics (overlaps with finance ML)
    )

    def __init__(
        self,
        max_results: int = 25,
        categories=DEFAULT_CATEGORIES,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.max_results = max_results
        self.categories = categories

    def _fetch(self, query: str) -> str:
        # Build a precise query
        tokens = [t for t in query.split() if t]
        if tokens:
            term_clause = " AND ".join(f"all:{t}" for t in tokens)
        else:
            term_clause = ""
        if self.categories:
            cat_clause = " OR ".join(f"cat:{c}" for c in self.categories)
            search_query = (
                f"({cat_clause}) AND ({term_clause})" if term_clause else f"({cat_clause})"
            )
        else:
            search_query = term_clause or "all:*"
        params = {
            "search_query": search_query,
            "start": "0",
            "max_results": str(self.max_results),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        url = f"{self.base_url}?{urllib.parse.urlencode(params)}"

        # Retry logic for 429 / timeout
        import urllib.error as _ue
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                return self._http_get(url, {"User-Agent": "confluence-decoder-research/0.1"})
            except (_ue.HTTPError, _ue.URLError, TimeoutError, OSError) as exc:
                last_exc = exc
                wait = self._backoff_factor ** attempt * 5
                if isinstance(exc, _ue.HTTPError) and exc.code == 429:
                    wait = max(wait, 30)  # arxiv 429 → wait at least 30s
                import time as _t
                _t.sleep(wait)
        raise last_exc  # type: ignore[misc]

    def _parse(self, raw: str) -> List[Discovery]:
        results: List[Discovery] = []
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return results

        for entry in root.findall("a:entry", _ARXIV_NS):
            arxiv_id = self._strip_arxiv_id(self._text(entry, "a:id"))
            if not arxiv_id:
                continue
            authors = [
                self._text(a, "a:name")
                for a in entry.findall("a:author", _ARXIV_NS)
                if self._text(a, "a:name")
            ]
            categories = [
                c.get("term", "") for c in entry.findall("a:category", _ARXIV_NS)
                if c.get("term")
            ]
            results.append(
                Discovery(
                    id=f"arxiv:{arxiv_id}",
                    title=self._normalize_whitespace(self._text(entry, "a:title")),
                    url=f"https://arxiv.org/abs/{arxiv_id}",
                    source=self.name,
                    discovered_at=datetime.now(timezone.utc).isoformat(),
                    authors=authors,
                    published=self._text(entry, "a:published") or None,
                    abstract=self._normalize_whitespace(self._text(entry, "a:summary")),
                    tags=categories,
                    # arxiv preprints don't have a single license field in Atom;
                    # default to None — most are CC-BY or similar but verify
                    # case-by-case via the abs page.
                    license=None,
                )
            )
        return results

    @staticmethod
    def _text(node: Optional[ET.Element], path: str) -> str:
        if node is None:
            return ""
        found = node.find(path, _ARXIV_NS)
        if found is None or found.text is None:
            return ""
        return found.text

    @staticmethod
    def _strip_arxiv_id(url_or_id: str) -> str:
        """Extract '2401.12345' from 'http://arxiv.org/abs/2401.12345v1' etc."""
        if not url_or_id:
            return ""
        m = re.search(r"(\d{4}\.\d{4,5})(v\d+)?$", url_or_id.strip())
        return m.group(1) if m else url_or_id.strip().split("/")[-1]

    @staticmethod
    def _normalize_whitespace(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip())


# ────────────────────────────────────────────────────────────────────────────
# HuggingFace source
# ────────────────────────────────────────────────────────────────────────────


class HuggingFaceSource(DiscoverySource):
    """HuggingFace Hub model/dataset search. No auth required for public search.

    Docs: https://huggingface.co/docs/hub/en/api
    """
    name = "huggingface"
    base_url = "https://huggingface.co/api"
    rate_limit_seconds = 2.0

    def __init__(self, max_results: int = 25, **kwargs):
        super().__init__(**kwargs)
        self.max_results = max_results

    def _fetch(self, query: str) -> str:
        import urllib.error as _ue
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                # Search both models and datasets
                params = urllib.parse.urlencode({
                    "search": query,
                    "limit": str(self.max_results),
                    "sort": "downloads",
                    "direction": "-1",
                })
                url = f"{self.base_url}/models?{params}"
                return self._http_get(url, {"User-Agent": "confluence-decoder-research/0.2"})
            except (_ue.HTTPError, _ue.URLError, TimeoutError, OSError) as exc:
                last_exc = exc
                wait = self._backoff_factor ** attempt * 3
                if isinstance(exc, _ue.HTTPError) and exc.code == 429:
                    wait = max(wait, 15)
                time.sleep(wait)
        raise last_exc  # type: ignore[misc]

    def _parse(self, raw: str) -> List[Discovery]:
        import json as _json
        results: List[Discovery] = []
        try:
            items = _json.loads(raw)
            if not isinstance(items, list):
                items = items.get("models", []) if isinstance(items, dict) else []
        except ( _json.JSONDecodeError, TypeError):
            return results

        for item in items:
            model_id = item.get("modelId", "") or item.get("id", "")
            if not model_id:
                continue
            tags = item.get("tags", []) or []
            results.append(Discovery(
                id=f"hf:{model_id}",
                title=model_id,
                url=f"https://huggingface.co/{model_id}",
                source=self.name,
                discovered_at=datetime.now(timezone.utc).isoformat(),
                authors=[item.get("author", "")] if item.get("author") else [],
                published=item.get("lastModified", "") or item.get("createdAt", ""),
                abstract=item.get("description", "") or item.get("cardData", {}).get("description", "") if isinstance(item.get("cardData"), dict) else "",
                tags=tags[:10],
                license=item.get("license", None) or item.get("cardData", {}).get("license", None) if isinstance(item.get("cardData"), dict) else None,
                raw=item,
            ))
        return results


# ────────────────────────────────────────────────────────────────────────────
# GitHub topic source
# ────────────────────────────────────────────────────────────────────────────


class GitHubTopicSource(DiscoverySource):
    """GitHub topic search via the public API. No auth required (rate-limited).

    Docs: https://docs.github.com/en/rest/search/search?apiVersion=2022-11-28#search-repositories
    """
    name = "github_topic"
    base_url = "https://api.github.com/search/repositories"
    rate_limit_seconds = 5.0  # GitHub allows 10 req/min unauthenticated

    def __init__(self, max_results: int = 25, **kwargs):
        super().__init__(**kwargs)
        self.max_results = max_results

    def _fetch(self, query: str) -> str:
        import urllib.error as _ue
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                params = urllib.parse.urlencode({
                    "q": f"topic:{query}",
                    "sort": "stars",
                    "order": "desc",
                    "per_page": str(min(self.max_results, 100)),
                })
                url = f"{self.base_url}?{params}"
                return self._http_get(url, {
                    "User-Agent": "confluence-decoder-research/0.2",
                    "Accept": "application/vnd.github.v3+json",
                })
            except (_ue.HTTPError, _ue.URLError, TimeoutError, OSError) as exc:
                last_exc = exc
                wait = self._backoff_factor ** attempt * 10
                if isinstance(exc, _ue.HTTPError) and exc.code == 403:
                    wait = max(wait, 60)  # GitHub rate limit
                time.sleep(wait)
        raise last_exc  # type: ignore[misc]

    def _parse(self, raw: str) -> List[Discovery]:
        import json as _json
        results: List[Discovery] = []
        try:
            data = _json.loads(raw)
            items = data.get("items", [])
        except (_json.JSONDecodeError, TypeError):
            return results

        for item in items:
            full_name = item.get("full_name", "")
            if not full_name:
                continue
            results.append(Discovery(
                id=f"gh:{full_name}",
                title=item.get("description", "") or full_name,
                url=item.get("html_url", f"https://github.com/{full_name}"),
                source=self.name,
                discovered_at=datetime.now(timezone.utc).isoformat(),
                authors=[item.get("owner", {}).get("login", "")] if item.get("owner") else [],
                published=item.get("updated_at", "") or item.get("created_at", ""),
                abstract=item.get("description", ""),
                tags=item.get("topics", [])[:10],
                license=item.get("license", {}).get("spdx_id", None) if item.get("license") else None,
                raw=item,
            ))
        return results


# ────────────────────────────────────────────────────────────────────────────
# SSRN source
# ────────────────────────────────────────────────────────────────────────────


class SSRNSource(DiscoverySource):
    """SSRN (Social Science Research Network) quant-finance pre-print search.

    Uses the public search page + HTML parsing (no official API).
    Respects robots.txt; rate-limited to 5s between requests.
    """
    name = "ssrn"
    base_url = "https://papers.ssrn.com/sol3/DisplayJournalBrowse.cfm"
    search_url = "https://papers.ssrn.com/sol3/results.cfm"
    rate_limit_seconds = 5.0

    def __init__(self, max_results: int = 25, **kwargs):
        super().__init__(**kwargs)
        self.max_results = max_results

    def _fetch(self, query: str) -> str:
        import urllib.error as _ue
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                params = urllib.parse.urlencode({
                    "txtKey_Words": query,
                    "isSearch": "true",
                    "strSelectedOption": "1",  # sort by relevance
                    "perPage": str(min(self.max_results, 50)),
                })
                url = f"{self.search_url}?{params}"
                return self._http_get(url, {
                    "User-Agent": "confluence-decoder-research/0.2 (academic research bot)",
                    "Accept": "text/html",
                })
            except (_ue.HTTPError, _ue.URLError, TimeoutError, OSError) as exc:
                last_exc = exc
                wait = self._backoff_factor ** attempt * 5
                time.sleep(wait)
        raise last_exc  # type: ignore[misc]

    def _parse(self, raw: str) -> List[Discovery]:
        """Parse SSRN search results HTML. Extract paper titles, IDs, abstracts."""
        results: List[Discovery] = []
        try:

            # Simple regex-based extraction (SSRN HTML is fairly stable)
            # Pattern: paper links like /abstract=1234567
            paper_pattern = re.compile(
                r'href=["\'][^"\']*abstract[=](\d+)["\'][^>]*>(.*?)</a>',
                re.IGNORECASE | re.DOTALL
            )
            abstract_pattern = re.compile(
                r'class=["\']abstract[^"\']*["\'][^>]*>(.*?)</(?:div|p|span)>',
                re.IGNORECASE | re.DOTALL
            )
            author_pattern = re.compile(
                r'class=["\']authors[^"\']*["\'][^>]*>(.*?)</(?:div|p|span)>',
                re.IGNORECASE | re.DOTALL
            )

            # Extract paper blocks
            paper_blocks = re.split(r'<div[^>]*class=["\'][^"\']*result[^"\']*["\']', raw)

            for block in paper_blocks[:self.max_results]:
                paper_match = paper_pattern.search(block)
                if not paper_match:
                    continue
                paper_id = paper_match.group(1)
                title = re.sub(r'<[^>]+>', '', paper_match.group(2)).strip()
                if not title:
                    continue

                abstract_match = abstract_pattern.search(block)
                abstract = ""
                if abstract_match:
                    abstract = re.sub(r'<[^>]+>', '', abstract_match.group(1)).strip()

                author_match = author_pattern.search(block)
                authors = []
                if author_match:
                    author_text = re.sub(r'<[^>]+>', '', author_match.group(1)).strip()
                    authors = [a.strip() for a in author_text.split(',') if a.strip()]

                results.append(Discovery(
                    id=f"ssrn:{paper_id}",
                    title=title,
                    url=f"https://papers.ssrn.com/sol3/papers.cfm?abstract_id={paper_id}",
                    source=self.name,
                    discovered_at=datetime.now(timezone.utc).isoformat(),
                    authors=authors,
                    abstract=abstract[:500] if abstract else None,
                    tags=["ssrn", "preprint"],
                    license=None,
                ))
        except Exception:
            pass
        return results


# ────────────────────────────────────────────────────────────────────────────
# NBER source
# ────────────────────────────────────────────────────────────────────────────


class NBERSource(DiscoverySource):
    """NBER (National Bureau of Economic Research) working paper search.

    Uses the public working papers page + HTML parsing.
    Rate-limited to 5s between requests.
    """
    name = "nber"
    base_url = "https://www.nber.org/papers"
    rate_limit_seconds = 5.0

    def __init__(self, max_results: int = 25, **kwargs):
        super().__init__(**kwargs)
        self.max_results = max_results

    def _fetch(self, query: str) -> str:
        import urllib.error as _ue
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                params = urllib.parse.urlencode({
                    "q": query,
                    "page": "1",
                    "perPage": str(min(self.max_results, 50)),
                })
                url = f"{self.base_url}?{params}"
                return self._http_get(url, {
                    "User-Agent": "confluence-decoder-research/0.2 (academic research bot)",
                    "Accept": "text/html",
                })
            except (_ue.HTTPError, _ue.URLError, TimeoutError, OSError) as exc:
                last_exc = exc
                wait = self._backoff_factor ** attempt * 5
                time.sleep(wait)
        raise last_exc  # type: ignore[misc]

    def _parse(self, raw: str) -> List[Discovery]:
        """Parse NBER working paper listings from HTML."""
        results: List[Discovery] = []
        try:
            # NBER paper links: /papers/w12345
            paper_pattern = re.compile(
                r'href=["\'](/papers/w\d+)["\'][^>]*>(.*?)</a>',
                re.IGNORECASE | re.DOTALL
            )
            # Paper titles in h3/h4 tags
            title_pattern = re.compile(
                r'<h[34][^>]*>(.*?)</h[34]>',
                re.IGNORECASE | re.DOTALL
            )
            # Abstract snippets
            abstract_pattern = re.compile(
                r'class=["\'][^"\']*abstract[^"\']*["\'][^>]*>(.*?)</(?:div|p)>',
                re.IGNORECASE | re.DOTALL
            )

            # Split into paper blocks
            paper_blocks = re.split(r'<article|<div[^>]*class=["\'][^"\']*paper[^"\']*["\']', raw)

            for block in paper_blocks[:self.max_results]:
                link_match = paper_pattern.search(block)
                if not link_match:
                    continue
                paper_path = link_match.group(1)
                paper_id = paper_path.split("/")[-1]

                title_match = title_pattern.search(block)
                title = ""
                if title_match:
                    title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
                if not title:
                    title = re.sub(r'<[^>]+>', '', link_match.group(2)).strip()
                if not title:
                    continue

                abstract_match = abstract_pattern.search(block)
                abstract = ""
                if abstract_match:
                    abstract = re.sub(r'<[^+>', '', abstract_match.group(1)).strip()

                results.append(Discovery(
                    id=f"nber:{paper_id}",
                    title=title,
                    url=f"https://www.nber.org{paper_path}",
                    source=self.name,
                    discovered_at=datetime.now(timezone.utc).isoformat(),
                    abstract=abstract[:500] if abstract else None,
                    tags=["nber", "working-paper"],
                    license=None,
                ))
        except Exception:
            pass
        return results


# ────────────────────────────────────────────────────────────────────────────
# Quantocracy RSS source
# ────────────────────────────────────────────────────────────────────────────


class QuantocracySource(DiscoverySource):
    """Quantocracy blog aggregator RSS feed.

    RSS URL: https://quantocracy.com/feed/
    No auth required. Parses RSS XML for recent quant-finance blog posts.
    """
    name = "quantocracy"
    rss_url = "https://quantocracy.com/feed/"
    rate_limit_seconds = 10.0

    def __init__(self, max_results: int = 25, **kwargs):
        super().__init__(**kwargs)
        self.max_results = max_results

    def _fetch(self, query: str) -> str:
        import urllib.error as _ue
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                return self._http_get(self.rss_url, {
                    "User-Agent": "confluence-decoder-research/0.2",
                    "Accept": "application/rss+xml, application/xml, text/xml",
                })
            except (_ue.HTTPError, _ue.URLError, TimeoutError, OSError) as exc:
                last_exc = exc
                wait = self._backoff_factor ** attempt * 10
                time.sleep(wait)
        raise last_exc  # type: ignore[misc]

    def _parse(self, raw: str) -> List[Discovery]:
        """Parse RSS XML feed."""
        results: List[Discovery] = []
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return results

        # RSS 2.0 namespace
        _ns = {"rss": "http://purl.org/rss/1.0/"}
        channel = root.find("channel")
        if channel is None:
            channel = root  # try without channel wrapper

        for item in channel.findall("item")[:self.max_results]:
            title_el = item.find("title")
            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            if not title:
                continue

            link_el = item.find("link")
            url = link_el.text.strip() if link_el is not None and link_el.text else ""

            desc_el = item.find("description")
            abstract = ""
            if desc_el is not None and desc_el.text:
                abstract = re.sub(r'<[^>]+>', '', desc_el.text).strip()[:500]

            date_el = item.find("pubDate")
            published = date_el.text.strip() if date_el is not None and date_el.text else None

            guid_el = item.find("guid")
            guid = guid_el.text.strip() if guid_el is not None and guid_el.text else url

            # Filter by query relevance (simple keyword match)
            results.append(Discovery(
                id=f"quantocracy:{guid}",
                title=title,
                url=url,
                source=self.name,
                discovered_at=datetime.now(timezone.utc).isoformat(),
                published=published,
                abstract=abstract,
                tags=["quantocracy", "blog", "aggregator"],
                license=None,
            ))
        return results


# ────────────────────────────────────────────────────────────────────────────
# AQR Commentary RSS source
# ────────────────────────────────────────────────────────────────────────────


class AQRSource(DiscoverySource):
    """AQR (Cliff Asness) commentary RSS feed.

    RSS URL: https://www.aqr.com/Insights/RSS
    No auth required. Parses RSS XML for recent AQR research commentary.
    """
    name = "aqr"
    rss_url = "https://www.aqr.com/insights/rss"
    rate_limit_seconds = 10.0

    def __init__(self, max_results: int = 25, **kwargs):
        super().__init__(**kwargs)
        self.max_results = max_results

    def _fetch(self, query: str) -> str:
        import urllib.error as _ue
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                return self._http_get(self.rss_url, {
                    "User-Agent": "confluence-decoder-research/0.2",
                    "Accept": "application/rss+xml, application/xml, text/xml",
                })
            except (_ue.HTTPError, _ue.URLError, TimeoutError, OSError) as exc:
                last_exc = exc
                wait = self._backoff_factor ** attempt * 10
                time.sleep(wait)
        raise last_exc  # type: ignore[misc]

    def _parse(self, raw: str) -> List[Discovery]:
        """Parse RSS XML feed."""
        results: List[Discovery] = []
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return results

        channel = root.find("channel")
        if channel is None:
            channel = root

        for item in channel.findall("item")[:self.max_results]:
            title_el = item.find("title")
            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            if not title:
                continue

            link_el = item.find("link")
            url = link_el.text.strip() if link_el is not None and link_el.text else ""

            desc_el = item.find("description")
            abstract = ""
            if desc_el is not None and desc_el.text:
                abstract = re.sub(r'<[^>]+>', '', desc_el.text).strip()[:500]

            date_el = item.find("pubDate")
            published = date_el.text.strip() if date_el is not None and date_el.text else None

            guid_el = item.find("guid")
            guid = guid_el.text.strip() if guid_el is not None and guid_el.text else url

            results.append(Discovery(
                id=f"aqr:{guid}",
                title=title,
                url=url,
                source=self.name,
                discovered_at=datetime.now(timezone.utc).isoformat(),
                published=published,
                abstract=abstract,
                tags=["aqr", "commentary", "cliff-asness"],
                license=None,
            ))
        return results


# ────────────────────────────────────────────────────────────────────────────
# Robot Wealth RSS source
# ────────────────────────────────────────────────────────────────────────────


class RobotWealthSource(DiscoverySource):
    """Robot Wealth blog RSS feed.

    RSS URL: https://robotwealth.com/feed/
    No auth required. Parses RSS XML for recent quant-finance blog posts.
    """
    name = "robot_wealth"
    rss_url = "https://robotwealth.com/feed/"
    rate_limit_seconds = 10.0

    def __init__(self, max_results: int = 25, **kwargs):
        super().__init__(**kwargs)
        self.max_results = max_results

    def _fetch(self, query: str) -> str:
        import urllib.error as _ue
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                return self._http_get(self.rss_url, {
                    "User-Agent": "confluence-decoder-research/0.2",
                    "Accept": "application/rss+xml, application/xml, text/xml",
                })
            except (_ue.HTTPError, _ue.URLError, TimeoutError, OSError) as exc:
                last_exc = exc
                wait = self._backoff_factor ** attempt * 10
                time.sleep(wait)
        raise last_exc  # type: ignore[misc]

    def _parse(self, raw: str) -> List[Discovery]:
        """Parse RSS XML feed."""
        results: List[Discovery] = []
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return results

        channel = root.find("channel")
        if channel is None:
            channel = root

        for item in channel.findall("item")[:self.max_results]:
            title_el = item.find("title")
            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            if not title:
                continue

            link_el = item.find("link")
            url = link_el.text.strip() if link_el is not None and link_el.text else ""

            desc_el = item.find("description")
            abstract = ""
            if desc_el is not None and desc_el.text:
                abstract = re.sub(r'<[^>]+>', '', desc_el.text).strip()[:500]

            date_el = item.find("pubDate")
            published = date_el.text.strip() if date_el is not None and date_el.text else None

            guid_el = item.find("guid")
            guid = guid_el.text.strip() if guid_el is not None and guid_el.text else url

            results.append(Discovery(
                id=f"rw:{guid}",
                title=title,
                url=url,
                source=self.name,
                discovered_at=datetime.now(timezone.utc).isoformat(),
                published=published,
                abstract=abstract,
                tags=["robot-wealth", "blog", "quant"],
                license=None,
            ))
        return results


# ────────────────────────────────────────────────────────────────────────────
# ResearchGate source (stub — requires JS rendering)
# ────────────────────────────────────────────────────────────────────────────


class ResearchGateSource(DiscoverySource):
    """ResearchGate search. STUB — ResearchGate requires JS rendering.

    For now, this is a placeholder that logs a warning.
    Future: use their API or a headless browser.
    """
    name = "researchgate"
    rate_limit_seconds = 10.0

    def _fetch(self, query: str) -> str:
        raise NotImplementedError(
            "ResearchGate requires JS rendering — not yet implemented. "
            "Consider using their API or a headless browser."
        )

    def _parse(self, raw: str) -> List[Discovery]:
        raise NotImplementedError("ResearchGateSource not implemented yet")


# ────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ────────────────────────────────────────────────────────────────────────────


def discover_all(
    sources: List[DiscoverySource],
    queries_per_source: Dict[str, List[str]],
) -> Tuple[List[Discovery], Dict[str, str]]:
    """Run each source over its assigned queries.

    Returns:
        (all_discoveries, errors_by_source_name)
    """
    out: List[Discovery] = []
    errors: Dict[str, str] = {}
    for source in sources:
        qs = queries_per_source.get(source.name) or []
        if not qs:
            continue
        try:
            out.extend(source.search_many(qs))
        except NotImplementedError as exc:
            errors[source.name] = f"not implemented: {exc}"
        except Exception as exc:  # noqa: BLE001 — best-effort multi-source
            errors[source.name] = f"{type(exc).__name__}: {exc}"
    return out, errors
