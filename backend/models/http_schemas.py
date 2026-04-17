"""Pydantic request/response schemas for the FastAPI HTTP surface.

Kept separate from ``api.py`` (the FastAPI app at repo root) so names stay clear.
"""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    openai: bool
    searxng: bool
    tavily: bool = False


class ResearchRequest(BaseModel):
    topic: str
    brief: str = ""
    max_layer: int = 3


class ResearchResponse(BaseModel):
    job_id: str
