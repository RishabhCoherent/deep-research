"""Domain → AuthorityTier lookup loaded from authority.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import yaml

from research.core.types import AuthorityTier

_YAML_PATH = Path(__file__).parent / "authority.yaml"

_TIER_ORDER = [
    AuthorityTier.GOVERNMENT,
    AuthorityTier.MULTILATERAL,
    AuthorityTier.INDUSTRY_BODY,
    AuthorityTier.TIER1_MEDIA,
    AuthorityTier.ANALYST_FIRM,
    AuthorityTier.TRADE_PRESS,
    AuthorityTier.BLOG,
]

_TIER_RANK: dict[AuthorityTier, int] = {t: i for i, t in enumerate(_TIER_ORDER)}


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(_YAML_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def get_authority_tier(url: str) -> AuthorityTier:
    """Return the AuthorityTier for a given URL based on domain rules."""
    try:
        hostname = urlparse(url).hostname or ""
    except Exception:
        return AuthorityTier.BLOG

    data = _load()

    for tier_str, rules in data.items():
        if tier_str == "blog":
            continue
        tier = AuthorityTier(tier_str)

        for suffix in rules.get("suffixes", []):
            if hostname.endswith(suffix):
                return tier

        for domain in rules.get("domains", []):
            if hostname == domain or hostname.endswith("." + domain):
                return tier

    return AuthorityTier.BLOG


def tier_rank(tier: AuthorityTier) -> int:
    """Lower rank = higher authority (0 = government)."""
    return _TIER_RANK.get(tier, len(_TIER_ORDER))
