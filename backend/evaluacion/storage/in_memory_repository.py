from __future__ import annotations

from threading import Lock

from evaluacion.contracts.models import UiFeedbackReportV1
from evaluacion.storage.base_repository import FeedbackRepository
from evaluacion.storage.models import FeedbackJobRecord


class InMemoryFeedbackRepository(FeedbackRepository):
    def __init__(self) -> None:
        self._jobs: dict[str, FeedbackJobRecord] = {}
        self._reports: dict[str, UiFeedbackReportV1] = {}
        self._lock = Lock()

    def create_job(self, *, evaluation_id: str, user_id: str, session_id: str, created_at: str) -> FeedbackJobRecord:
        with self._lock:
            record = FeedbackJobRecord(
                evaluation_id=evaluation_id,
                user_id=user_id,
                session_id=session_id,
                status="created",
                created_at=created_at,
                updated_at=created_at,
                error=None,
            )
            self._jobs[evaluation_id] = record
            return record

    def update_job_status(self, *, evaluation_id: str, status: str, updated_at: str, error: str | None = None) -> FeedbackJobRecord:
        with self._lock:
            job = self._jobs[evaluation_id]
            updated = job.model_copy(update={"status": status, "updated_at": updated_at, "error": error})
            self._jobs[evaluation_id] = updated
            return updated

    def patch_job_metadata(
        self,
        *,
        evaluation_id: str,
        artifacts: dict[str, str] | None = None,
        stage_latencies_ms: dict[str, int] | None = None,
        updated_at: str,
    ) -> FeedbackJobRecord:
        with self._lock:
            job = self._jobs[evaluation_id]
            merged_artifacts = dict(job.artifacts)
            merged_latencies = dict(job.stage_latencies_ms)
            if artifacts:
                merged_artifacts.update(artifacts)
            if stage_latencies_ms:
                merged_latencies.update(stage_latencies_ms)
            updated = job.model_copy(update={
                "artifacts": merged_artifacts,
                "stage_latencies_ms": merged_latencies,
                "updated_at": updated_at,
            })
            self._jobs[evaluation_id] = updated
            return updated

    def get_job(self, *, evaluation_id: str) -> FeedbackJobRecord | None:
        with self._lock:
            return self._jobs.get(evaluation_id)

    def save_report(self, *, evaluation_id: str, report: UiFeedbackReportV1) -> None:
        with self._lock:
            self._reports[evaluation_id] = report

    def get_report(self, *, evaluation_id: str) -> UiFeedbackReportV1 | None:
        with self._lock:
            return self._reports.get(evaluation_id)


REPOSITORY = InMemoryFeedbackRepository()
