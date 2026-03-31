"""Date template variables for prompt injection."""

from __future__ import annotations

from datetime import date


def date_vars() -> dict:
    """Return common date template variables. Use instead of local _date_vars()."""
    today = date.today()
    return {
        "current_date": today.strftime("%B %d, %Y"),
        "current_year": str(today.year),
        "last_year": str(today.year - 1),
        "next_year": str(today.year + 1),
    }
