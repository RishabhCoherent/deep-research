"""
Prompt constants — split into submodules by layer/purpose.

Re-exports all public symbols so `from prompts import X` works.
"""

from prompts.topic_rules import (
    TOPIC_QUALITY_RULES,
    TOPIC_QUESTION_RULES,
    TOPIC_INSIGHT_RULES,
    get_insight_rules,
    get_quality_rules,
    get_question_rules,
)
from prompts.topic_interpretation import (
    TOPIC_INTERPRETATION_PROMPT,
    REPORT_OUTLINE_PROMPT,
    SCOPE_DEFINITION_PROMPT,
)
from prompts.baseline import (
    BASELINE_SECTION_PLANNER_PROMPT,
    BASELINE_WRITE_PROMPT,
)
from prompts.enhanced import (
    ENHANCED_SYSTEM_PROMPT,
    LAYER1_SELF_REVIEW,
)
from prompts.evaluation import (
    EVALUATION_PROMPT,
    COMPARATIVE_EVALUATION_PROMPT,
    COMPARISON_SUMMARY,
    LAYER_COMPARISON_PROMPT,
    EXECUTIVE_COMPARISON_SUMMARY,
    REPORT_METRICS_PROMPT,
    CLAIM_PAIR_EXTRACTION_PROMPT,
    CLAIM_JOURNEY_EXTRACTION_PROMPT,
)
from prompts.langgraph_prompts import (
    L1_ENHANCEMENT_PROMPT,
)
