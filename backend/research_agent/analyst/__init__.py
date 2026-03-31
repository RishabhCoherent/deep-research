"""Analyst Agent — thinks like a consultant, not a search wrapper."""

# run_analyst imported lazily to avoid circular imports during development
__all__ = ["run_analyst"]


def run_analyst(*args, **kwargs):
    from research_agent.analyst.run import run_analyst as _run
    return _run(*args, **kwargs)
