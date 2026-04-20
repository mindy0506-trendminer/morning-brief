"""PR-3 Task 3 — enforce that every feed in ``config/sources.yml`` declares
an ISO-3166 alpha-3 ``country`` field. Regression guard: new feeds cannot
be added without a country assignment, otherwise the site would silently
fall back to the language default map and produce a wrong flag.
"""

from __future__ import annotations

import re
from pathlib import Path

from morning_brief.collector import load_sources


_ISO3_RE = re.compile(r"^[A-Z]{3}$")


def test_all_feeds_declare_country() -> None:
    sources_path = Path(__file__).parent.parent / "config" / "sources.yml"
    assert sources_path.exists(), f"sources.yml missing at {sources_path}"
    sources = load_sources(sources_path)
    assert sources, "sources.yml produced an empty list"

    missing: list[str] = []
    bad_shape: list[tuple[str, str]] = []
    for src in sources:
        name = src.get("name", "<unnamed>")
        country = src.get("country")
        if not country:
            missing.append(name)
            continue
        if not _ISO3_RE.match(country):
            bad_shape.append((name, country))

    assert not missing, (
        "feeds missing required 'country' field: " + ", ".join(missing)
    )
    assert not bad_shape, (
        "feeds with non-ISO3166-alpha-3 'country' value: "
        + ", ".join(f"{n}={v!r}" for n, v in bad_shape)
    )
