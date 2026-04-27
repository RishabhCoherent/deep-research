"""Pydantic schemas for Agent 5 sub-agent I/O validation."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from research.core.types import (
    Citation, NumericClaim, Observation,
    NewsEvent, RegulatoryChange, Disruption,
)

# ── Field-value normalisers (run before pydantic validates enums) ─────────────

_CATEGORY_MAP = {
    "merger": "m_and_a", "acquisition": "m_and_a", "mergers_acquisitions": "m_and_a",
    "ma": "m_and_a", "m&a": "m_and_a",
    "earning": "earnings", "financial_results": "earnings", "results": "earnings",
    "product_launch": "product", "launch": "product", "announcement": "product",
    "new_product": "product",
    "deal": "partnership", "joint_venture": "partnership", "collaboration": "partnership",
    "funding": "investment", "investment_round": "investment", "ipo": "investment",
    "news": "other", "general": "other", "regulatory": "other",
}

def _norm_category(v: str) -> str:
    k = v.lower().replace(" ", "_").replace("-", "_")
    if k in {"m_and_a", "earnings", "product", "partnership", "investment", "other"}:
        return k
    for prefix, mapped in _CATEGORY_MAP.items():
        if k.startswith(prefix) or k == prefix:
            return mapped
    return "other"

def _norm_impact(v: str) -> str:
    k = v.lower()
    return k if k in {"positive", "negative", "neutral", "mixed"} else "neutral"

def _norm_magnitude(v: str) -> str:
    k = v.lower()
    return k if k in {"low", "medium", "high"} else "medium"

def _norm_severity(v: str) -> str:
    k = v.lower()
    return k if k in {"watch", "elevated", "critical"} else "watch"

def _coerce_event(e: object) -> object:
    if not isinstance(e, dict):
        return e
    if "category" in e:
        e["category"] = _norm_category(str(e["category"]))
    if "impact" in e:
        e["impact"] = _norm_impact(str(e["impact"]))
    if "magnitude" in e:
        e["magnitude"] = _norm_magnitude(str(e["magnitude"]))
    if "headline" in e and isinstance(e["headline"], str):
        e["headline"] = e["headline"][:300]
    if "summary" in e and isinstance(e["summary"], str):
        e["summary"] = e["summary"][:500]
    # Ensure source is a dict with at least a url key
    if "source" not in e or not isinstance(e.get("source"), dict):
        e["source"] = {"url": "https://unknown.example.com", "authority_tier": "unknown"}
    return e

def _coerce_disruption(d: object) -> object:
    if not isinstance(d, dict):
        return d
    if "severity" in d:
        d["severity"] = _norm_severity(str(d["severity"]))
    if "upstream_node" in d and isinstance(d["upstream_node"], str):
        d["upstream_node"] = d["upstream_node"][:200]
    if "event" in d and isinstance(d["event"], str):
        d["event"] = d["event"][:400]
    if "supply_chain_path" in d and isinstance(d["supply_chain_path"], str):
        d["supply_chain_path"] = d["supply_chain_path"][:300]
    if "evidence" not in d or not isinstance(d["evidence"], list):
        d["evidence"] = []
    return d

def _coerce_reg_change(r: object) -> object:
    if not isinstance(r, dict):
        return r
    if "action" in r and isinstance(r["action"], str):
        r["action"] = r["action"][:400]
    if "impact_summary" in r and isinstance(r["impact_summary"], str):
        r["impact_summary"] = r["impact_summary"][:400]
    if "source" not in r or not isinstance(r.get("source"), dict):
        r["source"] = {"url": "https://unknown.example.com", "authority_tier": "unknown"}
    return r


# ── Schemas ───────────────────────────────────────────────────────────────────

class EventBundle(BaseModel):
    """Output of the event_hunter sub-agent (5a)."""
    events: list[NewsEvent] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_shape(cls, data):
        if isinstance(data, list):
            raw_events = data
        elif isinstance(data, dict):
            raw_events = data.get("events", [])
        else:
            return {"events": []}
        return {"events": [_coerce_event(e) for e in raw_events if isinstance(e, dict)]}


class RegulatoryBundle(BaseModel):
    """Output of the regulatory_tracker sub-agent (5b)."""
    changes: list[RegulatoryChange] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_shape(cls, data):
        if isinstance(data, list):
            raw = data
        elif isinstance(data, dict):
            raw = data.get("changes", [])
        else:
            return {"changes": []}
        return {"changes": [_coerce_reg_change(r) for r in raw if isinstance(r, dict)]}


class GeopoliticalBundle(BaseModel):
    """Output of the geopolitical_scanner sub-agent (5c)."""
    disruptions: list[Disruption] = Field(default_factory=list)
    scratchpad_writes: list[Observation] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_shape(cls, data):
        if not isinstance(data, dict):
            return {"disruptions": [], "scratchpad_writes": []}
        raw_d = data.get("disruptions", [])
        raw_s = data.get("scratchpad_writes", [])
        return {
            "disruptions": [_coerce_disruption(d) for d in raw_d if isinstance(d, dict)],
            "scratchpad_writes": raw_s,
        }

    @field_validator("scratchpad_writes")
    @classmethod
    def _news_section(cls, ws: list) -> list:
        return [w for w in ws if w.section == "news"]


class A5Output(BaseModel):
    """Final crew output — node patches RunState."""
    claims: list[NumericClaim]
    narrative: str
    scratchpad_writes: list[Observation]
