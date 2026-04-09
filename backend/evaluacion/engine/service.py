from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi import HTTPException

from sessions.state import get_session_state

from evaluacion.contracts.models import (
    CoreRunnerInputV1,
    FeedbackInputBundleV1,
    FeedbackReportCoreV1,
    Provenance,
    SessionRef,
    TrajectoryRunnerInputV1,
    TurnTrajectoryV1,
    UiFeedbackReportV1,
)
from evaluacion.domains.router import build_feedback_input_bundle_v1
from evaluacion.engine.assembler import assemble_ui_report
from evaluacion.engine.flow_config import (
    ASYNC_START_DELAY_MS,
    CORE_MODEL,
    CORE_PROMPT_VERSION,
    TRAJECTORY_MODEL,
    TRAJECTORY_PROMPT_VERSION,
)
from evaluacion.engine.input_shaping import shape_core_input, shape_trajectory_input
from evaluacion.engine.job_states import now_iso
from evaluacion.engine.provenance import stable_hash
from evaluacion.engine.reconciliation import reconcile_outputs
from evaluacion.engine.runners import run_core_evaluator, run_trajectory_evaluator
from evaluacion.engine.validators import validate_core_business, validate_trajectory_business
from evaluacion.storage import REPOSITORY
from evaluacion.storage.models import FeedbackJobRecord

_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="feedback_eval")
_LAUNCH_LOCK = threading.Lock()


def _set_status(evaluation_id: str, status: str, *, error: str | None = None) -> FeedbackJobRecord:
    return REPOSITORY.update_job_status(evaluation_id=evaluation_id, status=status, updated_at=now_iso(), error=error)


def _patch(evaluation_id: str, *, artifacts: dict[str, str] | None = None, stage_latencies_ms: dict[str, int] | None = None) -> None:
    REPOSITORY.patch_job_metadata(
        evaluation_id=evaluation_id,
        artifacts=artifacts,
        stage_latencies_ms=stage_latencies_ms,
        updated_at=now_iso(),
    )


def _run_pipeline_from_bundle(*, evaluation_id: str, bundle: FeedbackInputBundleV1) -> None:
    try:
        if ASYNC_START_DELAY_MS > 0:
            time.sleep(ASYNC_START_DELAY_MS / 1000.0)

        t0 = time.perf_counter()
        _set_status(evaluation_id, "building_inputs")
        core_input: CoreRunnerInputV1 = shape_core_input(bundle)
        trajectory_input: TrajectoryRunnerInputV1 = shape_trajectory_input(bundle)
        _patch(
            evaluation_id,
            artifacts={
                "bundle_hash": stable_hash(bundle.model_dump(mode="json")),
                "core_input_hash": stable_hash(core_input.model_dump(mode="json")),
                "trajectory_input_hash": stable_hash(trajectory_input.model_dump(mode="json")),
                "flow_id": str(bundle.domain_context.flow_id or ""),
                "context_id": str(bundle.domain_context.context_id or ""),
                "context_version": str(bundle.domain_context.context_version or ""),
                "resolution_source": str(bundle.domain_context.resolution_source or ""),
                "fallback_used": str(bool(bundle.domain_context.fallback_used)).lower(),
            },
            stage_latencies_ms={"building_inputs": int((time.perf_counter() - t0) * 1000)},
        )

        turn_indexes = {t.turn_index for t in bundle.conversation.turns}

        t1 = time.perf_counter()
        _set_status(evaluation_id, "running_core")
        core_output: FeedbackReportCoreV1
        core_output, core_source = run_core_evaluator(core_input)
        validate_core_business(core_output, turn_indexes=turn_indexes or {1})
        _patch(
            evaluation_id,
            artifacts={
                "core_output_hash": stable_hash(core_output.model_dump(mode="json")),
                "core_source": core_source,
            },
            stage_latencies_ms={"running_core": int((time.perf_counter() - t1) * 1000)},
        )

        t2 = time.perf_counter()
        _set_status(evaluation_id, "running_trajectory")
        trajectory_output: TurnTrajectoryV1
        trajectory_output, trajectory_source = run_trajectory_evaluator(trajectory_input)
        validate_trajectory_business(trajectory_output, turn_indexes=turn_indexes or {1})
        _patch(
            evaluation_id,
            artifacts={
                "trajectory_output_hash": stable_hash(trajectory_output.model_dump(mode="json")),
                "trajectory_source": trajectory_source,
            },
            stage_latencies_ms={"running_trajectory": int((time.perf_counter() - t2) * 1000)},
        )

        t3 = time.perf_counter()
        _set_status(evaluation_id, "assembling_report")
        trajectory_reconciled = reconcile_outputs(
            core=core_output,
            trajectory=trajectory_output,
            turn_count=max(len(bundle.conversation.turns), 1),
        )
        job = REPOSITORY.get_job(evaluation_id=evaluation_id)
        if job is None:
            raise ValueError("job_lost")
        artifacts = job.artifacts

        provenance = Provenance(
            evaluation_id=evaluation_id,
            bundle_hash=artifacts.get("bundle_hash", ""),
            core_input_hash=artifacts.get("core_input_hash", ""),
            trajectory_input_hash=artifacts.get("trajectory_input_hash", ""),
            core_output_hash=artifacts.get("core_output_hash", ""),
            trajectory_output_hash=artifacts.get("trajectory_output_hash", ""),
            core_model=CORE_MODEL,
            trajectory_model=TRAJECTORY_MODEL,
            core_prompt_version=CORE_PROMPT_VERSION,
            trajectory_prompt_version=TRAJECTORY_PROMPT_VERSION,
            flow_id=bundle.domain_context.flow_id,
            context_id=bundle.domain_context.context_id,
            context_version=bundle.domain_context.context_version,
            resolution_source=bundle.domain_context.resolution_source,
            fallback_used=bundle.domain_context.fallback_used,
        )
        report: UiFeedbackReportV1 = assemble_ui_report(
            core=core_output,
            trajectory=trajectory_reconciled,
            provenance=provenance,
        )
        REPOSITORY.save_report(evaluation_id=evaluation_id, report=report)
        _patch(
            evaluation_id,
            stage_latencies_ms={"assembling_report": int((time.perf_counter() - t3) * 1000)},
        )
        _set_status(evaluation_id, "completed")
    except Exception as exc:
        _set_status(evaluation_id, "failed", error=f"pipeline_error:{type(exc).__name__}:{exc}")


def _run_pipeline(*, evaluation_id: str, user_id: str, session_id: str) -> None:
    state = get_session_state(user_id=user_id, session_id=session_id)
    bundle: FeedbackInputBundleV1 = build_feedback_input_bundle_v1(state=state, evaluation_id=evaluation_id)
    _run_pipeline_from_bundle(evaluation_id=evaluation_id, bundle=bundle)


def _launch_pipeline_task(*, evaluation_id: str, job_fn, kwargs: dict[str, object]) -> FeedbackJobRecord:
    _set_status(evaluation_id, "queued")
    with _LAUNCH_LOCK:
        _EXECUTOR.submit(job_fn, evaluation_id=evaluation_id, **kwargs)
    job = REPOSITORY.get_job(evaluation_id=evaluation_id)
    if job is None:
        raise RuntimeError("feedback_job_not_found_after_submit")
    return job


def create_evaluation(*, user_id: str, session_id: str) -> FeedbackJobRecord:
    evaluation_id = str(uuid4())
    REPOSITORY.create_job(
        evaluation_id=evaluation_id,
        user_id=user_id,
        session_id=session_id,
        created_at=now_iso(),
    )
    return _launch_pipeline_task(
        evaluation_id=evaluation_id,
        job_fn=_run_pipeline,
        kwargs={"user_id": user_id, "session_id": session_id},
    )


def create_evaluation_from_bundle(*, bundle: FeedbackInputBundleV1, owner_label: str) -> FeedbackJobRecord:
    evaluation_id = str(uuid4())
    bundle_for_job = bundle.model_copy(update={"evaluation_id": evaluation_id, "session_ref": SessionRef(user_id="dev_fixture", session_id=owner_label)})
    REPOSITORY.create_job(
        evaluation_id=evaluation_id,
        user_id="dev_fixture",
        session_id=owner_label,
        created_at=now_iso(),
    )
    return _launch_pipeline_task(
        evaluation_id=evaluation_id,
        job_fn=_run_pipeline_from_bundle,
        kwargs={"bundle": bundle_for_job},
    )


def get_evaluation_status(*, evaluation_id: str) -> FeedbackJobRecord:
    job = REPOSITORY.get_job(evaluation_id=evaluation_id)
    if job is None:
        raise HTTPException(status_code=404, detail="evaluation_not_found")
    return job


def get_evaluation_report(*, evaluation_id: str) -> UiFeedbackReportV1:
    job = REPOSITORY.get_job(evaluation_id=evaluation_id)
    if job is None:
        raise HTTPException(status_code=404, detail="evaluation_not_found")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail=f"evaluation_not_completed:{job.status}")
    report = REPOSITORY.get_report(evaluation_id=evaluation_id)
    if report is None:
        raise HTTPException(status_code=404, detail="evaluation_report_not_found")
    return report
