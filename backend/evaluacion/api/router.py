from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

from evaluacion.api.models import (
    CreateEvaluationRequest,
    CreateEvaluationResponse,
    DevCreateEvaluationRequest,
    DevCreateEvaluationResponse,
    DevFixtureSummary,
    DevFixturesListResponse,
    EvaluationReportResponse,
    EvaluationStatusResponse,
)
from evaluacion.dev_fixtures.loader import get_fixture_by_id, list_fixtures
from evaluacion.engine import (
    create_evaluation,
    create_evaluation_from_bundle,
    get_evaluation_report,
    get_evaluation_status,
)
from evaluacion.engine.demo_adapter import fixture_to_bundle

router = APIRouter(prefix="/feedback", tags=["feedback"])


def _dev_fixtures_enabled() -> bool:
    return os.getenv("ENABLE_FEEDBACK_DEV_FIXTURES", "0").strip() in {"1", "true", "TRUE", "yes", "YES"}


def _guard_dev_route() -> None:
    if not _dev_fixtures_enabled():
        raise HTTPException(status_code=404, detail="feedback_dev_fixtures_disabled")


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


@router.get("/dev/fixtures", response_model=DevFixturesListResponse)
def list_feedback_dev_fixtures() -> DevFixturesListResponse:
    _guard_dev_route()
    fixtures = list_fixtures()
    payload = [
        DevFixtureSummary(
            fixture_id=f.fixture_id,
            title=f.title,
            domain=f.domain,
            turn_count=len(f.conversation.turns),
        )
        for f in fixtures
    ]
    return DevFixturesListResponse(fixtures=payload)


@router.post("/dev/evaluations", response_model=DevCreateEvaluationResponse)
def create_feedback_dev_evaluation(payload: DevCreateEvaluationRequest) -> DevCreateEvaluationResponse:
    _guard_dev_route()
    fixture = get_fixture_by_id(payload.fixture_id)
    if fixture is None:
        raise HTTPException(status_code=404, detail="feedback_dev_fixture_not_found")
    bundle = fixture_to_bundle(fixture=fixture, evaluation_id="pending")
    job = create_evaluation_from_bundle(bundle=bundle, owner_label=payload.fixture_id)
    return DevCreateEvaluationResponse(evaluation_id=job.evaluation_id, status=job.status, fixture_id=payload.fixture_id)
