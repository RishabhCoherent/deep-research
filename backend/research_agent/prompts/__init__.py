"""
Prompt constants — split into submodules by layer/purpose.

Re-exports all public symbols so existing imports like
  `from research_agent.prompts import BASELINE_WRITE_PROMPT`
continue to work unchanged.
"""

from research_agent.prompts.topic_rules import (
    TOPIC_QUALITY_RULES,
    TOPIC_QUESTION_RULES,
    TOPIC_INSIGHT_RULES,
    get_insight_rules,
    get_quality_rules,
    get_question_rules,
)
from research_agent.prompts.topic_interpretation import (
    TOPIC_INTERPRETATION_PROMPT,
    REPORT_OUTLINE_PROMPT,
    SCOPE_DEFINITION_PROMPT,
)
from research_agent.prompts.baseline_prompts import (
    BASELINE_SECTION_PLANNER_PROMPT,
    BASELINE_WRITE_PROMPT,
)
from research_agent.prompts.enhanced_prompts import (
    ENHANCED_SYSTEM_PROMPT,
    LAYER1_SELF_REVIEW,
)
from research_agent.prompts.evaluation_prompts import (
    EVALUATION_PROMPT,
    COMPARATIVE_EVALUATION_PROMPT,
    COMPARISON_SUMMARY,
    LAYER_COMPARISON_PROMPT,
    EXECUTIVE_COMPARISON_SUMMARY,
    REPORT_METRICS_PROMPT,
    CLAIM_PAIR_EXTRACTION_PROMPT,
    CLAIM_JOURNEY_EXTRACTION_PROMPT,
)
from research_agent.prompts.phase_prompts import (
    PHASE1_PLAN_PROMPT,
    PHASE2_EXTRACT_PROMPT,
    PHASE2_SCRAPE_EXTRACT_PROMPT,
    PHASE3_VERIFY_PROMPT,
    PHASE3_INSIGHT_PROMPT,
    PHASE4_WRITE_PROMPT,
    PHASE4_REVIEW_PROMPT,
)
from research_agent.prompts.langgraph_prompts import (
    L1_ENHANCEMENT_PROMPT,
    L2_DEEPDIVE_PROMPT,
)
from research_agent.prompts.expert_prompts import (
    EXPERT_DISSECT_PROMPT,
    EXPERT_TOPIC_PLAN_PROMPT,
    EXPERT_PLAN_PROMPT,
    EXPERT_SECTION_INVESTIGATE_PROMPT,
    EXPERT_INVESTIGATE_PROMPT,
    EXPERT_SYNTHESIZE_PROMPT,
    EXPERT_COMPOSE_PROMPT,
    EXPERT_EDITORIAL_REVIEW_PROMPT,
    EXPERT_TARGETED_REWRITE_PROMPT,
    EXPERT_VERIFY_PROMPT,
    REPORT_FORMAT_PROMPT,
)
