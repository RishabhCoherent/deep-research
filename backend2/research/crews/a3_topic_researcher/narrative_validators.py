"""Post-LLM validators for narrative quality (deterministic, no LLM)."""

from __future__ import annotations

import re
from research.core.types import Footnote


def assert_word_count(narrative: str, lo: int = 400, hi: int = 800) -> None:
    """Assert narrative word count is within [lo, hi]."""
    n = len(narrative.split())
    assert lo <= n <= hi, f"narrative word count {n} is outside [{lo}, {hi}]"


def assert_footnote_integrity(narrative: str, footnotes: list[Footnote]) -> None:
    """Assert every [N] used in narrative has a matching footnote, and vice versa."""
    used = {int(m.group(1)) for m in re.finditer(r"\[(\d{1,2})\]", narrative)}
    declared = {f.n for f in footnotes}
    missing = used - declared
    extra = declared - used
    assert not missing, f"footnote IDs used in narrative but not declared: {sorted(missing)}"
    assert not extra,   f"footnotes declared but never cited in narrative: {sorted(extra)}"


def word_count(narrative: str) -> int:
    return len(narrative.split())
