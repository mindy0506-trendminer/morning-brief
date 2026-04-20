"""Schema validation for config/companies.yml (plan v2 §D3 / PR-1 Task 1)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from morning_brief.models import CompanyTag


_COMPANIES_YML = Path(__file__).parent.parent / "config" / "companies.yml"

_VALID_CLASSES: set[str] = {"대기업", "유통", "혁신스타트업"}

_CANONICAL_CATEGORIES: set[str] = {
    "식음료",
    "뷰티",
    "패션",
    "라이프스타일",
    "소비트렌드",
    "MacroTrends",
}


@pytest.fixture(scope="module")
def loaded() -> dict:
    assert _COMPANIES_YML.exists(), f"companies.yml missing at {_COMPANIES_YML}"
    with _COMPANIES_YML.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class TestTopLevelSchema:
    def test_has_schema_version(self, loaded):
        assert loaded.get("schema_version") == "v1"

    def test_classes_match_canonical_set(self, loaded):
        assert set(loaded["classes"]) == _VALID_CLASSES

    def test_has_minimum_seed_count(self, loaded):
        # PR-1 requires ≥30 seed companies.
        assert len(loaded["companies"]) >= 30


class TestCompanyEntries:
    def test_every_entry_has_required_fields(self, loaded):
        for entry in loaded["companies"]:
            assert "name" in entry, entry
            assert "class" in entry, entry
            assert "aliases" in entry, entry
            assert "categories" in entry, entry

    def test_class_is_in_three_class_set(self, loaded):
        for entry in loaded["companies"]:
            assert entry["class"] in _VALID_CLASSES, entry

    def test_categories_draw_from_canonical_set(self, loaded):
        for entry in loaded["companies"]:
            for cat in entry["categories"]:
                assert cat in _CANONICAL_CATEGORIES, (entry["name"], cat)

    def test_aliases_is_list_and_non_empty(self, loaded):
        for entry in loaded["companies"]:
            assert isinstance(entry["aliases"], list), entry["name"]
            # Every seed company deserves at least one alias surface form
            # (an empty alias list would neutralize the company_tags collector).
            assert len(entry["aliases"]) >= 1, entry["name"]

    def test_names_are_unique(self, loaded):
        names = [entry["name"] for entry in loaded["companies"]]
        assert len(names) == len(set(names)), (
            "Duplicate company name in companies.yml"
        )


class TestRoundTripToCompanyTag:
    """Every seed entry's class should be a valid CompanyTag class."""

    def test_every_class_accepted_by_model(self, loaded):
        for entry in loaded["companies"]:
            tag = CompanyTag.model_validate(
                {
                    "name": entry["name"],
                    "class": entry["class"],
                    "confidence": 1.0,
                }
            )
            assert tag.name == entry["name"]
            assert tag.class_ == entry["class"]
