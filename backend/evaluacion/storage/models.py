from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from evaluacion.contracts.models import JobStatus, UiFeedbackReportV1


class FeedbackJobRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_id: str
    user_id: str
    session_id: str
    status: JobStatus
    created_at: str
    updated_at: str
    error: str | None = None
    stage_latencies_ms: dict[str, int] = Field(default_factory=dict)
    artifacts: dict[str, str] = Field(default_factory=dict)


class FeedbackJobDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job: FeedbackJobRecord
    report: UiFeedbackReportV1 | None = None
