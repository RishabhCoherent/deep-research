"""Custom exceptions for the research system."""


class ResearchError(Exception):
    """Base exception for all research system errors."""
    pass


class BudgetExceeded(ResearchError):
    """Raised when the cost budget is exceeded."""
    def __init__(self, current_cost: float, budget: float):
        self.current_cost = current_cost
        self.budget = budget
        super().__init__(f"Budget exceeded: ${current_cost:.2f} > ${budget:.2f}")


class CitationRequired(ResearchError):
    """Raised when a claim lacks proper citation."""
    pass


class CrewFailure(ResearchError):
    """Raised when a CrewAI crew fails to complete."""
    pass


class ValidationError(ResearchError):
    """Raised when Pydantic validation fails."""
    pass


class ToolError(ResearchError):
    """Raised when a tool execution fails."""
    pass


class StateError(ResearchError):
    """Raised when there's an issue with RunState."""
    pass
