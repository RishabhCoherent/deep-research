"""
Token usage tracking and cost calculation for multi-layer research agent.

Pricing per 1M tokens (as of 2025):
  gpt-4o           : $2.50 input,  $10.00 output
  gpt-4o-mini      : $0.15 input,  $0.60 output
  gpt-4.1          : $2.00 input,  $8.00 output
  gpt-4.1-mini     : $0.40 input,  $1.60 output
  gpt-4.1-nano     : $0.10 input,  $0.40 output
  o3-mini          : $1.10 input,  $4.40 output
  o4-mini          : $1.10 input,  $4.40 output
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Pricing: (input_per_1M, output_per_1M)
MODEL_PRICING = {
    "gpt-4o":           (2.50,  10.00),
    "gpt-4o-mini":      (0.15,   0.60),
    "gpt-4.1":          (2.00,   8.00),
    "gpt-4.1-mini":     (0.40,   1.60),
    "gpt-4.1-nano":     (0.10,   0.40),
    "o3-mini":          (1.10,   4.40),
    "o4-mini":          (1.10,   4.40),
}


@dataclass
class TokenUsage:
    """Tracks token usage across multiple LLM calls."""
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    calls: int = 0
    model: str = ""

    def add(self, input_tok: int, output_tok: int, model: str = "",
            reasoning_tok: int = 0):
        self.input_tokens += input_tok
        self.output_tokens += output_tok
        self.reasoning_tokens += reasoning_tok
        self.calls += 1
        if model:
            self.model = model

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.reasoning_tokens

    @property
    def cost_usd(self) -> float:
        """Calculate cost based on model pricing.

        Reasoning tokens are billed at the output token rate.
        """
        model = self.model or "gpt-4o"
        # Find the best matching pricing key
        pricing = MODEL_PRICING.get(model)
        if not pricing:
            # Try prefix match (e.g., "gpt-4o-2024-08-06" -> "gpt-4o")
            for key in MODEL_PRICING:
                if model.startswith(key):
                    pricing = MODEL_PRICING[key]
                    break
        if not pricing:
            pricing = (2.50, 10.00)  # Default to gpt-4o pricing

        input_cost = (self.input_tokens / 1_000_000) * pricing[0]
        output_cost = (self.output_tokens / 1_000_000) * pricing[1]
        reasoning_cost = (self.reasoning_tokens / 1_000_000) * pricing[1]
        return input_cost + output_cost + reasoning_cost

    def __str__(self) -> str:
        parts = (f"{self.calls} calls | {self.input_tokens:,} in + "
                 f"{self.output_tokens:,} out")
        if self.reasoning_tokens > 0:
            parts += f" + {self.reasoning_tokens:,} reasoning"
        parts += f" = {self.total_tokens:,} tokens | ${self.cost_usd:.4f}"
        return parts


@dataclass
class CostTracker:
    """Aggregates token usage across all layers."""
    layers: dict[str, TokenUsage] = field(default_factory=dict)

    def get(self, label: str) -> TokenUsage:
        if label not in self.layers:
            self.layers[label] = TokenUsage()
        return self.layers[label]

    @property
    def total_input(self) -> int:
        return sum(u.input_tokens for u in self.layers.values())

    @property
    def total_output(self) -> int:
        return sum(u.output_tokens for u in self.layers.values())

    @property
    def total_reasoning(self) -> int:
        return sum(u.reasoning_tokens for u in self.layers.values())

    @property
    def total_tokens(self) -> int:
        return self.total_input + self.total_output + self.total_reasoning

    @property
    def total_cost(self) -> float:
        return sum(u.cost_usd for u in self.layers.values())

    @property
    def total_calls(self) -> int:
        return sum(u.calls for u in self.layers.values())

    def format_table(self) -> str:
        """Format cost breakdown as ASCII table."""
        has_reasoning = self.total_reasoning > 0

        if has_reasoning:
            header = (f"{'Component':<20} | {'Calls':>5} | {'Input':>10} | "
                      f"{'Output':>10} | {'Reasoning':>10} | {'Cost':>10}")
        else:
            header = (f"{'Component':<20} | {'Calls':>5} | {'Input':>10} | "
                      f"{'Output':>10} | {'Cost':>10}")
        sep = "-" * len(header)
        rows = [sep, header, sep]

        for label, usage in sorted(self.layers.items()):
            if has_reasoning:
                rows.append(
                    f"{label:<20} | {usage.calls:>5} | "
                    f"{usage.input_tokens:>10,} | {usage.output_tokens:>10,} | "
                    f"{usage.reasoning_tokens:>10,} | "
                    f"${usage.cost_usd:>8.4f}"
                )
            else:
                rows.append(
                    f"{label:<20} | {usage.calls:>5} | "
                    f"{usage.input_tokens:>10,} | {usage.output_tokens:>10,} | "
                    f"${usage.cost_usd:>8.4f}"
                )

        rows.append(sep)
        if has_reasoning:
            rows.append(
                f"{'TOTAL':<20} | {self.total_calls:>5} | "
                f"{self.total_input:>10,} | {self.total_output:>10,} | "
                f"{self.total_reasoning:>10,} | "
                f"${self.total_cost:>8.4f}"
            )
        else:
            rows.append(
                f"{'TOTAL':<20} | {self.total_calls:>5} | "
                f"{self.total_input:>10,} | {self.total_output:>10,} | "
                f"${self.total_cost:>8.4f}"
            )
        rows.append(sep)
        return "\n".join(rows)


def extract_usage(response) -> tuple[int, int, str, int]:
    """Extract token counts, model name, and reasoning tokens from a LangChain LLM response.

    Returns:
        (input_tokens, output_tokens, model_name, reasoning_tokens)

    Reasoning tokens are internal chain-of-thought tokens used by models
    like o4-mini, o3-mini, and potentially gpt-4.1. They are billed at
    the output token rate but are not visible in the response content.
    """
    input_tok = 0
    output_tok = 0
    reasoning_tok = 0
    model = ""

    # LangChain ChatOpenAI response
    meta = getattr(response, "usage_metadata", None)
    if meta:
        input_tok = meta.get("input_tokens", 0)
        output_tok = meta.get("output_tokens", 0)

        # LangChain exposes reasoning tokens in output_token_details
        output_details = meta.get("output_token_details", {})
        if isinstance(output_details, dict):
            reasoning_tok = output_details.get("reasoning", 0) or 0

    resp_meta = getattr(response, "response_metadata", None)
    if resp_meta:
        model = resp_meta.get("model_name", "")

        # Fallback: some versions use token_usage
        if not input_tok:
            tu = resp_meta.get("token_usage", {})
            input_tok = tu.get("prompt_tokens", 0)
            output_tok = tu.get("completion_tokens", 0)

        # Fallback for reasoning tokens from OpenAI's raw response
        if not reasoning_tok:
            tu = resp_meta.get("token_usage", {})
            completion_details = tu.get("completion_tokens_details", {})
            if isinstance(completion_details, dict):
                reasoning_tok = completion_details.get("reasoning_tokens", 0) or 0

    return input_tok, output_tok, model, reasoning_tok


# Module-level singleton tracker -- layers record usage here
_global_tracker = CostTracker()


def get_tracker() -> CostTracker:
    """Return the global cost tracker."""
    return _global_tracker


def reset_tracker():
    """Reset the global cost tracker for a new run."""
    global _global_tracker
    _global_tracker = CostTracker()


def track(label: str, response):
    """Record token usage from an LLM response into the global tracker."""
    input_tok, output_tok, model, reasoning_tok = extract_usage(response)
    _global_tracker.get(label).add(input_tok, output_tok, model, reasoning_tok)
