"""Scratchpad read/write tools for cross-agent observation sharing."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Optional

from langchain_core.tools import tool

from research.core.types import Observation, Citation

_SCRATCHPAD: dict[str, list[dict]] = defaultdict(list)


def reset_scratchpad() -> None:
    """Clear all sections. Call before each a3/a4/a5 node run."""
    _SCRATCHPAD.clear()


def get_observations(section: str) -> list[Observation]:
    """Return all Observation objects accumulated under a section."""
    return [Observation.model_validate(d) for d in _SCRATCHPAD.get(section, [])]


def get_all_observations() -> list[Observation]:
    """Return every observation across all sections."""
    result = []
    for entries in _SCRATCHPAD.values():
        for d in entries:
            result.append(Observation.model_validate(d))
    return result


@tool
def scratchpad_read(section: str) -> str:
    """Read observations written to a scratchpad section by any agent.

    Args:
        section: One of 'topic', 'market_context', or 'news'.

    Returns:
        JSON array of Observation objects, or empty array if none exist.
    """
    entries = _SCRATCHPAD.get(section, [])
    return json.dumps(entries, default=str)


@tool
def scratchpad_write(observation_json: str) -> str:
    """Write a single observation to the shared scratchpad.

    Args:
        observation_json: JSON string matching the Observation schema:
            {"section": "topic"|"market_context"|"news",
             "key": str (max 120 chars),
             "value": str (max 400 chars),
             "written_by": str,
             "citation": {url, title, authority_tier} | null}

    Returns:
        Confirmation string.
    """
    try:
        obs = Observation.model_validate_json(observation_json)
        _SCRATCHPAD[obs.section].append(obs.model_dump())
        return f"OK: observation written to section='{obs.section}', key='{obs.key}'"
    except Exception as exc:
        return f"ERROR: could not write observation — {exc}"
