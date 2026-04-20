"""Acceptance tests for morning_brief/collector.py — Steps 3."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from morning_brief.collector import (
    extract_entities,
    load_brands,
    load_categories,
    parse_entries,
    unwrap_google_news_url,
)
from morning_brief.models import Article

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONFIG_DIR = Path(__file__).parent.parent / "config"


def _make_article(
    title: str = "",
    raw_summary: str = "",
    enriched_text: str | None = None,
    language: str = "ko",
    source_type: str = "TraditionalMedia",
    category: str | None = None,
) -> Article:
    now = datetime(2026, 4, 18, 9, 0, 0)
    return Article(
        id="test-id",
        title=title,
        source_name="TestSource",
        source_type=source_type,  # type: ignore[arg-type]
        url="https://example.com/article",
        canonical_url="https://example.com/article",
        language=language,  # type: ignore[arg-type]
        published_at=now,
        category=category,
        raw_summary=raw_summary,
        enriched_text=enriched_text,
        fetched_at=now,
        extracted_entities=[],
    )


# ---------------------------------------------------------------------------
# Test 1: load_brands
# ---------------------------------------------------------------------------


class TestLoadBrands:
    def test_load_brands_korean_alias(self):
        """brands.txt has '자라=Zara' → load_brands()['자라'] == 'Zara'."""
        brands = load_brands(_CONFIG_DIR / "brands.txt")
        assert brands["자라"] == "Zara"

    def test_load_brands_canonical_lowercase(self):
        """brands.txt has '자라=Zara' → load_brands()['zara'] == 'Zara'."""
        brands = load_brands(_CONFIG_DIR / "brands.txt")
        assert brands["zara"] == "Zara"

    def test_load_brands_bare_canonical(self):
        """Bare 'Nike' line → brands['nike'] == 'Nike'."""
        brands = load_brands(_CONFIG_DIR / "brands.txt")
        assert brands["nike"] == "Nike"

    def test_load_brands_bare_samsung(self):
        """Bare 'Samsung' → brands['samsung'] == 'Samsung'."""
        brands = load_brands(_CONFIG_DIR / "brands.txt")
        assert brands["samsung"] == "Samsung"


# ---------------------------------------------------------------------------
# Test 2: extract_entities — English
# ---------------------------------------------------------------------------


class TestExtractEntitiesEnglish:
    def test_samsung_galaxy_extracted(self):
        """Article with title 'Samsung unveils Galaxy S26' → Samsung and Galaxy extracted."""
        brands = load_brands(_CONFIG_DIR / "brands.txt")
        article = _make_article(
            title="Samsung unveils Galaxy S26",
            language="en",
        )
        display_forms, _ = extract_entities(article, brands)
        assert "Samsung" in display_forms
        assert "Galaxy" in display_forms

    def test_multi_word_entity(self):
        """'Apple Inc launches new product' extracts 'Apple' (brand normalized)."""
        brands = load_brands(_CONFIG_DIR / "brands.txt")
        article = _make_article(title="Apple launches new product", language="en")
        display_forms, _ = extract_entities(article, brands)
        assert "Apple" in display_forms


# ---------------------------------------------------------------------------
# Test 3: extract_entities — Korean brand override
# ---------------------------------------------------------------------------


class TestExtractEntitiesKoreanBrandOverride:
    def test_zara_override(self):
        """Article body '자라 신상 공개' with brands 자라→Zara yields 'Zara', not '자라'."""
        brands = load_brands(_CONFIG_DIR / "brands.txt")
        article = _make_article(
            title="자라 신상 공개",
            raw_summary="자라 신상 공개",
            language="ko",
        )
        display_forms, _ = extract_entities(article, brands)
        assert "Zara" in display_forms
        assert "자라" not in display_forms

    def test_uniqlo_override(self):
        """유니클로 mentioned → 'Uniqlo' returned."""
        brands = load_brands(_CONFIG_DIR / "brands.txt")
        article = _make_article(
            title="유니클로 신상품 출시",
            raw_summary="유니클로가 새 라인을 발표했다.",
            language="ko",
        )
        display_forms, _ = extract_entities(article, brands)
        assert "Uniqlo" in display_forms


# ---------------------------------------------------------------------------
# Test 4: extract_entities — cross-language R6
# ---------------------------------------------------------------------------


class TestExtractEntitiesCrossLanguage:
    def test_english_entities_in_korean_article(self):
        """R6: article.language='ko' with EN brand names still extracts them via EN regex."""
        brands = load_brands(_CONFIG_DIR / "brands.txt")
        article = _make_article(
            title="Samsung Galaxy S26가 한국에 출시됐다",
            language="ko",  # Korean-language article
        )
        display_forms, _ = extract_entities(article, brands)
        # English extractor MUST fire even on Korean-language articles
        assert "Samsung" in display_forms
        assert "Galaxy" in display_forms

    def test_both_extractors_fire(self):
        """Mixed article with both Korean brand and English brand → both captured."""
        brands = load_brands(_CONFIG_DIR / "brands.txt")
        article = _make_article(
            title="자라와 Nike의 협업",
            raw_summary="자라와 Nike가 콜라보를 발표했다.",
            language="ko",
        )
        display_forms, _ = extract_entities(article, brands)
        assert "Zara" in display_forms
        assert "Nike" in display_forms


# ---------------------------------------------------------------------------
# Test 5: category assignment
# ---------------------------------------------------------------------------


class TestCategoryAssignment:
    def test_fashion_keyword_ko(self):
        """Article title containing '패션' → category='패션'."""
        categories = load_categories(_CONFIG_DIR / "categories.yml")
        brands = load_brands(_CONFIG_DIR / "brands.txt")
        raw_entry = {
            "_source_name": "TestSource",
            "_source_type": "TraditionalMedia",
            "_language": "ko",
            "_category_hint": None,  # no hint → keyword matching
            "_status": "confirmed",
            "link": "https://example.com/fashion",
            "title": "패션 트렌드 2026 분석",
            "summary": "올해 패션 시장의 변화를 살펴봅니다.",
            "published_parsed": None,
        }
        articles = parse_entries([raw_entry], categories, brands, http_client=None)
        assert len(articles) == 1
        assert articles[0].category == "패션"

    def test_food_keyword_en(self):
        """English article with 'restaurant' → category='식음료' (PR-2 QA Issue C)."""
        categories = load_categories(_CONFIG_DIR / "categories.yml")
        brands = load_brands(_CONFIG_DIR / "brands.txt")
        raw_entry = {
            "_source_name": "TestSource",
            "_source_type": "TraditionalMedia",
            "_language": "en",
            "_category_hint": None,
            "_status": "confirmed",
            "link": "https://example.com/food",
            "title": "Restaurant chains face new competition",
            "summary": "The restaurant industry is changing fast.",
            "published_parsed": None,
        }
        articles = parse_entries([raw_entry], categories, brands, http_client=None)
        assert len(articles) == 1
        assert articles[0].category == "식음료"

    def test_category_hint_overrides_keyword(self):
        """If category_hint set, it is used directly regardless of keywords."""
        categories = load_categories(_CONFIG_DIR / "categories.yml")
        brands = load_brands(_CONFIG_DIR / "brands.txt")
        raw_entry = {
            "_source_name": "TestSource",
            "_source_type": "TraditionalMedia",
            "_language": "en",
            "_category_hint": "라이프스타일",
            "_status": "confirmed",
            "link": "https://example.com/hotel",
            "title": "Beauty salon opens near fashion district",  # misleading keywords
            "summary": "Hotel group expands.",
            "published_parsed": None,
        }
        articles = parse_entries([raw_entry], categories, brands, http_client=None)
        assert articles[0].category == "라이프스타일"


# ---------------------------------------------------------------------------
# Test 6: unwrap_google_news_url fallback
# ---------------------------------------------------------------------------


class TestGoogleNewsUnwrap:
    def test_fallback_on_exception(self, mocker):
        """On httpx exception, unwrap_google_news_url returns original URL."""
        import httpx

        mock_client = mocker.MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = httpx.ConnectError("connection refused")

        original_url = "https://news.google.com/rss/articles/CBMiSAB?hl=ko&gl=KR&ceid=KR%3Ako"
        result = unwrap_google_news_url(original_url, mock_client)
        assert result == original_url

    def test_non_google_url_passthrough(self, mocker):
        """Non-Google-News URLs are returned unchanged without HTTP calls."""
        import httpx

        mock_client = mocker.MagicMock(spec=httpx.Client)
        url = "https://www.businessoffashion.com/articles/some-article/"
        result = unwrap_google_news_url(url, mock_client)
        assert result == url
        mock_client.get.assert_not_called()

    def test_location_header_followed(self, mocker):
        """When Location header is present, that URL is returned."""
        import httpx

        mock_client = mocker.MagicMock(spec=httpx.Client)
        mock_response = mocker.MagicMock()
        mock_response.headers = {"Location": "https://publisher.com/real-article"}
        mock_response.text = ""
        mock_client.get.return_value = mock_response

        url = "https://news.google.com/rss/articles/CBMiSAB?hl=ko"
        result = unwrap_google_news_url(url, mock_client)
        assert result == "https://publisher.com/real-article"
