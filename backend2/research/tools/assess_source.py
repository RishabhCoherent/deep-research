"""assess_source tool: maps a URL to its AuthorityTier."""

from langchain_core.tools import tool
from research.pipeline.authority import get_authority_tier
from research.core.types import AuthorityTier


@tool
def assess_source(url: str) -> str:
    """Return the authority tier for a given URL.

    Args:
        url: The full URL of the source to assess.

    Returns:
        Authority tier string: one of government, multilateral, industry_body,
        tier1_media, analyst_firm, trade_press, blog.
    """
    tier: AuthorityTier = get_authority_tier(url)
    return tier.value
