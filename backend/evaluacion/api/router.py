from __future__ import annotations

from fastapi import APIRouter

from evaluacion.api.models import (
    CreateEvaluationRequest,
    CreateEvaluationResponse,
    EvaluationReportResponse,
    EvaluationStatusResponse,
)
from evaluacion.engine import create_evaluation, get_evaluation_report, get_evaluation_status

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("/evaluations", response_model=CreateEvaluationResponse)
def create_feedback_evaluation(payload: CreateEvaluationRequest) -> CreateEvaluationResponse:
    job = create_evaluation(user_id=payload.user_id, session_id=payload.session_id)
    return CreateEvaluationResponse(evaluation_id=job.evaluation_id, status=job.status)


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationStatusResponse)
def get_feedback_evaluation_status(evaluation_id: str) -> EvaluationStatusResponse:
    job = get_evaluation_status(evaluation_id=evaluation_id)
    return EvaluationStatusResponse(
        evaluation_id=job.evaluation_id,
        user_id=job.user_id,
        session_id=job.session_id,
        status=job.status,
        created_at=job.created_at,
        updated_at=job.updated_at,
        error=job.error,
        stage_latencies_ms=job.stage_latencies_ms,
    )


@router.get("/evaluations/{evaluation_id}/report", response_model=EvaluationReportResponse)
def get_feedback_evaluation_report(evaluation_id: str) -> EvaluationReportResponse:
    job = get_evaluation_status(evaluation_id=evaluation_id)
    report = get_evaluation_report(evaluation_id=evaluation_id)
    return EvaluationReportResponse(evaluation_id=evaluation_id, status=job.status, report=report)
