"""Collector: fetch RSS feeds, parse articles, enrich, and extract entities."""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import feedparser
import httpx
import yaml
from bs4 import BeautifulSoup

from morning_brief.db import upsert_article, upsert_entity_history
from morning_brief.models import Article

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

_SOURCES_PATH = Path("config/sources.yml")
_CATEGORIES_PATH = Path("config/categories.yml")
_BRANDS_PATH = Path("config/brands.txt")


def load_sources(path: Path = _SOURCES_PATH) -> list[dict]:
    """Load and return the list of source dicts from sources.yml."""
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data.get("sources", [])


def load_categories(path: Path = _CATEGORIES_PATH) -> dict[str, list[str]]:
    """Return {category_name: [keywords]} from categories.yml."""
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    result: dict[str, list[str]] = {}
    for cat_name, cat_data in data.get("categories", {}).items():
        result[cat_name] = cat_data.get("keywords", [])
    return result


def load_brands(path: Path = _BRANDS_PATH) -> dict[str, str]:
    """Return {alias_or_canonical_lower: canonical} from brands.txt.

    For lines like ``자라=Zara``, both ``자라`` (lowercased) and ``zara`` map to ``Zara``.
    For bare lines like ``Nike``, ``nike`` maps to ``Nike``.
    """
    mapping: dict[str, str] = {}
    with path.open(encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                alias, _, canonical = line.partition("=")
                alias = alias.strip()
                canonical = canonical.strip()
                mapping[alias.lower()] = canonical
                mapping[canonical.lower()] = canonical
            else:
                canonical = line.strip()
                mapping[canonical.lower()] = canonical
    return mapping


# ---------------------------------------------------------------------------
# RSS fetching
# ---------------------------------------------------------------------------

_RETRY_DELAYS = (1.0, 2.0, 4.0)
_HOST_LAST_REQUEST: dict[str, float] = {}


def _host_of(url: str) -> str:
    return urlparse(url).hostname or url


def _rate_limit(url: str) -> None:
    """Sleep if needed to stay at ≤ 1 request/s per host."""
    host = _host_of(url)
    last = _HOST_LAST_REQUEST.get(host)
    now = time.monotonic()
    if last is not None and (now - last) < 1.0:
        time.sleep(1.0 - (now - last))
    _HOST_LAST_REQUEST[host] = time.monotonic()


def fetch_feeds(
    sources: list[dict],
    http_client: httpx.Client,
) -> tuple[list[dict], list[str]]:
    """Fetch all RSS feeds and return (raw_entries, errors).

    Each entry dict is a feedparser entry extended with source metadata keys:
    ``_source_name``, ``_source_type``, ``_language``, ``_category_hint``,
    ``_status``.
    """
    raw_entries: list[dict] = []
    errors: list[str] = []

    for source in sources:
        url: str = source["url"]
        name: str = source.get("name", url)
        status: str = source.get("status", "confirmed")

        text: str | None = None
        for attempt, delay in enumerate([0.0] + list(_RETRY_DELAYS)):
            if delay:
                time.sleep(delay)
            try:
                _rate_limit(url)
                resp = http_client.get(url)
                resp.raise_for_status()
                text = resp.text
                break
            except Exception as exc:
                err_msg = f"[{name}] attempt {attempt + 1} failed: {exc}"
                logger.warning(err_msg)
                if attempt == len(_RETRY_DELAYS):
                    # Final attempt failed
                    err_msg = f"[{name}] all retries exhausted: {exc}"
                    errors.append(err_msg)
                    if status == "uncertain":
                        logger.info("[%s] uncertain source failed — skipping", name)
                    else:
                        logger.error(err_msg)
                    text = None
                    break

        if text is None:
            continue

        try:
            feed = feedparser.parse(text)
        except Exception as exc:
            errors.append(f"[{name}] feedparser error: {exc}")
            continue

        for entry in feed.entries:
            entry_dict = dict(entry)
            entry_dict["_source_name"] = source.get("name", "")
            entry_dict["_source_type"] = source.get("source_type", "TraditionalMedia")
            entry_dict["_language"] = source.get("language", "en")
            entry_dict["_country"] = source.get("country")
            entry_dict["_category_hint"] = source.get("category_hint")
            entry_dict["_status"] = status
            raw_entries.append(entry_dict)

    return raw_entries, errors


# ---------------------------------------------------------------------------
# Google News unwrap
# ---------------------------------------------------------------------------

_GOOGLE_NEWS_HOST = "news.google.com"
_ALLOWED_SCHEMES = {"http", "https"}


def _is_safe_outbound_url(url: str) -> bool:
    """Reject non-http(s) schemes and loopback / link-local / internal hosts.

    Used to vet Google News redirect Location headers and enrichment URLs
    before issuing outbound requests (guards against SSRF-style targets).
    """
    try:
        p = urlparse(url)
    except Exception:
        return False
    if p.scheme not in _ALLOWED_SCHEMES:
        return False
    host = (p.hostname or "").lower()
    if not host or host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return False
    if host.endswith(".local") or host.endswith(".internal"):
        return False
    return True


def unwrap_google_news_url(url: str, http_client: httpx.Client) -> str:
    """Resolve a Google News RSS redirect to the publisher's URL.

    Falls back to ``url`` on any error or when the resolved target fails the
    outbound-URL safety check.
    """
    parsed = urlparse(url)
    if parsed.hostname != _GOOGLE_NEWS_HOST:
        return url

    try:
        resp = http_client.get(url, follow_redirects=False, timeout=3.0)
        # Check Location header first
        location = resp.headers.get("location") or resp.headers.get("Location")
        if location and _is_safe_outbound_url(location):
            return location
        # Fallback: parse meta refresh
        soup = BeautifulSoup(resp.text, "html.parser")
        meta = soup.find("meta", attrs={"http-equiv": re.compile(r"refresh", re.I)})
        if meta and meta.get("content"):
            content = meta["content"]
            match = re.search(r"url=(.+)", content, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                if _is_safe_outbound_url(candidate):
                    return candidate
    except Exception as exc:
        logger.debug("unwrap_google_news_url failed for %s: %s", url, exc)

    return url


# ---------------------------------------------------------------------------
# HTML cleaning
# ---------------------------------------------------------------------------

_PAYWALL_MARKERS = (
    "subscribe",
    "login-required",
    "meter-paywall",
    "tp-modal",
    "paywall",
)


def _strip_html(html: str, max_chars: int = 1000) -> str:
    """Strip HTML tags and return plain text, truncated to max_chars."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return text[:max_chars]


def _is_paywalled(resp: httpx.Response, soup: BeautifulSoup) -> bool:
    """Detect common paywall signals."""
    if len(resp.content) < 2048:
        return True
    html_lower = resp.text.lower()
    for marker in _PAYWALL_MARKERS:
        if marker in html_lower:
            return True
    # Check class attributes
    for tag in soup.find_all(True):
        classes = tag.get("class", [])
        if isinstance(classes, list):
            for cls in classes:
                if "paywall" in cls.lower():
                    return True
    return False


# ---------------------------------------------------------------------------
# Article parsing
# ---------------------------------------------------------------------------


def _assign_category(
    category_hint: str | None,
    title: str,
    raw_summary: str,
    categories: dict[str, list[str]],
) -> str | None:
    """Return category string. Uses hint first, then keyword matching."""
    if category_hint:
        return category_hint
    combined = (title + " " + raw_summary).lower()
    best_cat: str | None = None
    best_hits = 0
    for cat_name, keywords in categories.items():
        hits = sum(1 for kw in keywords if kw.lower() in combined)
        if hits > best_hits:
            best_hits = hits
            best_cat = cat_name
    return best_cat if best_hits > 0 else None


def _get_published_at(entry: dict) -> datetime:
    """Parse published_at from feedparser entry, fallback to utcnow."""
    published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if published_parsed:
        try:
            import calendar

            ts = calendar.timegm(published_parsed)
            return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        except Exception:
            pass
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_entries(
    raw_entries: list[dict],
    categories: dict[str, list[str]],
    brands: dict[str, str],
    http_client: httpx.Client | None = None,
) -> list[Article]:
    """Convert raw feedparser entry dicts into Article objects.

    Deduplicates by canonical_url (first seen wins).
    """
    seen_urls: set[str] = set()
    articles: list[Article] = []

    for entry in raw_entries:
        raw_url: str = entry.get("link", "") or ""
        category_hint: str | None = entry.get("_category_hint")
        language: str = entry.get("_language", "en")
        source_name: str = entry.get("_source_name", "")
        source_type: str = entry.get("_source_type", "TraditionalMedia")
        source_country: str | None = entry.get("_country")

        # Unwrap Google News if client available
        if http_client is not None:
            canonical_url = unwrap_google_news_url(raw_url, http_client)
        else:
            canonical_url = raw_url

        # Dedup
        if canonical_url in seen_urls:
            continue
        seen_urls.add(canonical_url)

        # Title
        title: str = entry.get("title", "").strip()

        # raw_summary: prefer summary, fall back to description
        raw_html = (
            entry.get("summary")
            or entry.get("description")
            or ""
        )
        raw_summary = _strip_html(raw_html, max_chars=1000)

        # published_at
        published_at = _get_published_at(entry)

        # category
        category = _assign_category(category_hint, title, raw_summary, categories)

        article = Article(
            id=str(uuid.uuid4()),
            title=title,
            source_name=source_name,
            source_type=source_type,  # type: ignore[arg-type]
            url=raw_url,
            canonical_url=canonical_url,
            language=language,  # type: ignore[arg-type]
            published_at=published_at,
            category=category,
            raw_summary=raw_summary,
            enriched_text=None,
            fetched_at=datetime.now(timezone.utc).replace(tzinfo=None),
            extracted_entities=[],
            source_country=source_country,
        )
        articles.append(article)

    return articles


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------


def enrich_top_n(
    articles: list[Article],
    http_client: httpx.Client,
    n: int = 40,
    errors: list[str] | None = None,
) -> None:
    """Fetch HTML for top-N (by recency) articles, extract enriched_text in-place."""
    if errors is None:
        errors = []

    sorted_articles = sorted(
        articles,
        key=lambda a: a.published_at,
        reverse=True,
    )[:n]

    for article in sorted_articles:
        url = article.canonical_url or article.url
        if not url:
            continue
        if not _is_safe_outbound_url(url):
            errors.append(f"enrich [{url}]: unsafe outbound URL — skipping")
            continue
        try:
            resp = http_client.get(url, timeout=5.0, follow_redirects=True)
            resp.raise_for_status()
        except Exception as exc:
            errors.append(f"enrich [{url}]: {exc}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        if _is_paywalled(resp, soup):
            errors.append(f"enrich [{url}]: paywall detected — skipping")
            continue

        parts: list[str] = []
        # og:description
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            parts.append(og_desc["content"].strip())
        # first <p>
        first_p = soup.find("p")
        if first_p:
            parts.append(first_p.get_text(strip=True))

        enriched = " ".join(parts)[:2000]
        if enriched:
            article.enriched_text = enriched


# ---------------------------------------------------------------------------
# Entity extraction (R6 — cross-language)
# ---------------------------------------------------------------------------

# English: capitalize-start, 3+ chars for first token, optional following caps words
_EN_ENTITY_RE = re.compile(r"[A-Z][A-Za-z]{2,}(?:\s+[A-Z][A-Za-z]+){0,3}")

# Korean postpositions to strip
_KO_POSTPOSITIONS = re.compile(
    r"(은|는|이|가|을|를|의|에|와|과|로|으로|에서|부터|까지|보다|처럼|만|도)$"
)

# Hangul unicode block
_HANGUL_RE = re.compile(r"[\uAC00-\uD7A3]+")

# Quoted Korean (2+ Hangul chars in quotes) OR 2+ Hangul followed by subject/topic marker
_KO_QUOTED_RE = re.compile(
    r"""["'"'](?P<q>[\uAC00-\uD7A3]{2,})["'"']"""
    r"""|(?P<u>[\uAC00-\uD7A3]{2,})(?=은|는|이|가)"""
)


def _normalize_entity(text: str) -> str:
    """Return lowercase NFC-normalized entity string."""
    return unicodedata.normalize("NFC", text).lower()


def extract_entities(
    article: Article,
    brands: dict[str, str],
) -> tuple[list[str], list[str]]:
    """Extract entities from article using BOTH EN and KO extractors (R6).

    Returns (display_forms, normalized_forms). Brand-dict override applied.
    Deduplicates by normalized form.
    """
    combined_text = (
        (article.title or "")
        + " "
        + (article.raw_summary or "")
        + " "
        + (article.enriched_text or "")
    )

    collected: dict[str, str] = {}  # norm -> display

    # --- English extractor ---
    # Single-word pattern for sub-token extraction
    _en_word_re = re.compile(r"[A-Z][A-Za-z]{2,}")
    for match in _EN_ENTITY_RE.finditer(combined_text):
        raw = match.group(0)
        # Emit the full multi-word match
        norm = _normalize_entity(raw)
        display = brands.get(norm, raw)
        norm2 = _normalize_entity(display)
        if norm2 not in collected:
            collected[norm2] = display
        # Also emit each individual capitalized word so tests can assert 'Samsung'
        # and 'Galaxy' separately from 'Samsung Galaxy S26'
        for token in _en_word_re.findall(raw):
            t_norm = _normalize_entity(token)
            t_display = brands.get(t_norm, token)
            t_norm2 = _normalize_entity(t_display)
            if t_norm2 not in collected:
                collected[t_norm2] = t_display

    # --- Korean extractor ---
    # (a) brand key lookup: scan brand dict for Korean entries found in text
    for key, canonical in brands.items():
        if _HANGUL_RE.search(key) and key in combined_text:
            norm = _normalize_entity(canonical)
            if norm not in collected:
                collected[norm] = canonical

    # (b) quoted sequences and subject/topic-marked Hangul
    for match in _KO_QUOTED_RE.finditer(combined_text):
        raw = match.group("q") or match.group("u")
        if not raw:
            continue
        # Strip postpositions
        raw = _KO_POSTPOSITIONS.sub("", raw)
        if len(raw) < 2:
            continue
        # Brand override
        norm = _normalize_entity(raw)
        display = brands.get(norm, raw)
        norm2 = _normalize_entity(display)
        if norm2 not in collected:
            collected[norm2] = display

    display_forms = list(collected.values())
    norm_forms = list(collected.keys())
    return display_forms, norm_forms


# ---------------------------------------------------------------------------
# Entity ingest
# ---------------------------------------------------------------------------


def ingest_entities(
    conn: Any,
    articles: list[Article],
    brands: dict[str, str],
    now: datetime,
) -> None:
    """Extract entities for each article, update article.extracted_entities, upsert to DB."""
    for article in articles:
        display_forms, norm_forms = extract_entities(article, brands)
        article.extracted_entities = display_forms
        for display, norm in zip(display_forms, norm_forms):
            upsert_entity_history(conn, norm, display, article.id, now)


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


def collect(
    conn: Any,
    now: datetime,
    dry_run: bool = False,
) -> tuple[list[Article], list[str]]:
    """Fetch feeds, parse, enrich, extract entities, upsert to DB.

    Returns (articles, errors). In dry_run mode loads sample_articles.json fixture.
    """
    if dry_run:
        # Load cross-lingual pair fixture FIRST so its Zara articles take the
        # leading candidate IDs in the deterministic precluster ordering (they
        # must map to cand_001/cand_002 for the mock Call A response).
        fixture_dir = Path("tests/fixtures")
        cross_path = fixture_dir / "cross_lingual_pair.json"
        sample_path = fixture_dir / "sample_articles.json"

        raw: list[dict] = []
        seen_ids: set[str] = set()
        for path in (cross_path, sample_path):
            if not path.exists():
                continue
            for item in json.loads(path.read_text(encoding="utf-8")):
                aid = item.get("id")
                if aid and aid in seen_ids:
                    continue
                if aid:
                    seen_ids.add(aid)
                raw.append(item)

        if not raw:
            return [], []

        articles = [Article.model_validate(a) for a in raw]
        # Upsert to DB so selector and summarizer can work with it
        brands: dict[str, str] = {}
        try:
            brands = load_brands()
        except Exception:
            pass
        ingest_entities(conn, articles, brands, now)
        for article in articles:
            upsert_article(conn, article)
        return articles, []

    sources = load_sources()
    categories = load_categories()
    brands = load_brands()

    with httpx.Client(timeout=8.0, follow_redirects=True) as client:
        raw_entries, errors = fetch_feeds(sources, client)
        articles = parse_entries(raw_entries, categories, brands, http_client=client)
        enrich_top_n(articles, client, n=40, errors=errors)

    ingest_entities(conn, articles, brands, now)

    for article in articles:
        upsert_article(conn, article)

    return articles, errors
