"""Pydantic request/response schemas for the FastAPI layer."""

from pydantic import BaseModel


class SectionPlanSummary(BaseModel):
    number: int
    type: str
    title: str


class ExtractionSummary(BaseModel):
    report_title: str
    subtitle: str
    section_count: int
    sheet_count: int
    sheets: list[str]
    plans: list[SectionPlanSummary]


class ExtractionResponse(BaseModel):
    extracted_data: dict
    summary: ExtractionSummary


class GenerateRequest(BaseModel):
    extracted_data: dict
    skip_content: bool = False
    topic_override: str = ""


class GenerateResponse(BaseModel):
    job_id: str


class HealthResponse(BaseModel):
    openai: bool
    searxng: bool


# ─── Research Agent Models ────────────────────────────────────


class ResearchRequest(BaseModel):
    topic: str
    max_layer: int = 3


class ResearchResponse(BaseModel):
    job_id: str
