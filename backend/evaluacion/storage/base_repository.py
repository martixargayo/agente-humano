from __future__ import annotations

from abc import ABC, abstractmethod

from evaluacion.contracts.models import UiFeedbackReportV1
from evaluacion.storage.models import FeedbackJobRecord


class FeedbackRepository(ABC):
    @abstractmethod
    def create_job(self, *, evaluation_id: str, user_id: str, session_id: str, created_at: str) -> FeedbackJobRecord:
        raise NotImplementedError

    @abstractmethod
    def update_job_status(self, *, evaluation_id: str, status: str, updated_at: str, error: str | None = None) -> FeedbackJobRecord:
        raise NotImplementedError

    @abstractmethod
    def patch_job_metadata(
        self,
        *,
        evaluation_id: str,
        artifacts: dict[str, str] | None = None,
        stage_latencies_ms: dict[str, int] | None = None,
        updated_at: str,
    ) -> FeedbackJobRecord:
        raise NotImplementedError

    @abstractmethod
    def get_job(self, *, evaluation_id: str) -> FeedbackJobRecord | None:
        raise NotImplementedError

    @abstractmethod
    def save_report(self, *, evaluation_id: str, report: UiFeedbackReportV1) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_report(self, *, evaluation_id: str) -> UiFeedbackReportV1 | None:
        raise NotImplementedError
