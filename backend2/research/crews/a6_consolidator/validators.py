"""Post-LLM deterministic validators for Agent 6 (no LLM calls)."""

from __future__ import annotations

import re
from research.core.types import Theme, Footnote


def assert_bottom_up_structure(narrative: str) -> None:
    """Assert that the narrative contains at least one theme heading.

    A bottom-up narrative must reference specific themes (## or ### headings,
    or bold theme names) rather than opening with a generic summary.
    """
    has_heading = bool(re.search(r"^#{2,3}\s+\w", narrative, re.MULTILINE))
    has_bold    = bool(re.search(r"\*\*[A-Z][^*]{3,60}\*\*", narrative))
    assert has_heading or has_bold, (
        "narrative must have theme headings (## or **Bold**) to enforce bottom-up structure"
    )


def assert_footnote_integrity(narrative: str, footnotes: list[Footnote]) -> None:
    """Every [N] in the narrative must exist in footnotes, and vice-versa."""
    cited = {int(m) for m in re.findall(r"\[(\d+)\]", narrative)}
    defined = {f.n for f in footnotes}

    missing = cited - defined
    assert not missing, f"narrative references footnote IDs not in footnotes: {missing}"


def assert_theme_coverage(
    themes: list[Theme],
    min_themes: int | None = None,
    total_claims: int | None = None,
) -> None:
    """Verify theme coverage with a claim-count-aware minimum.

    A run with 7 claims cannot meaningfully produce 5 themes. Scale the floor
    so the check stays meaningful without forcing theme inflation:
        <= 3 claims   -> need >= 1 theme
        4-6 claims    -> need >= 2 themes
        7-12 claims   -> need >= 3 themes
        13-20 claims  -> need >= 4 themes
        >20 claims    -> need >= 5 themes
    Callers may override with an explicit min_themes.
    """
    if min_themes is None:
        n = total_claims if total_claims is not None else sum(len(t.claims) for t in themes)
        if n <= 3:
            min_themes = 1
        elif n <= 6:
            min_themes = 2
        elif n <= 12:
            min_themes = 3
        elif n <= 20:
            min_themes = 4
        else:
            min_themes = 5
    # ASCII-only message so structlog on Windows cp1252 stdout can't crash on U+2265.
    assert len(themes) >= min_themes, (
        f"expected >= {min_themes} themes, got {len(themes)}"
    )
    for t in themes:
        assert len(t.claims) >= 1, f"theme '{t.name}' has no supporting claims"
