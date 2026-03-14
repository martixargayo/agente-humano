from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from evaluacion.contracts.models import JobStatus, UiFeedbackReportV1


class CreateEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    session_id: str


class CreateEvaluationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluation_id: str
    status: JobStatus


class EvaluationStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluation_id: str
    user_id: str
    session_id: str
    status: JobStatus
    created_at: str
    updated_at: str
    error: str | None = None
    stage_latencies_ms: dict[str, int] = Field(default_factory=dict)


class EvaluationReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluation_id: str
    status: JobStatus
    report: UiFeedbackReportV1
