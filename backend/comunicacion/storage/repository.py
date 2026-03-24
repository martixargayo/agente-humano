from __future__ import annotations

from threading import Lock

from .models import AttemptRecord, DerivedArtifactRecord, RecordingRecord


class CommunicationRepositoryError(RuntimeError):
    pass


class AttemptNotFoundError(CommunicationRepositoryError):
    pass


class RecordingNotFoundError(CommunicationRepositoryError):
    pass


class InMemoryCommunicationRepository:
    def __init__(self) -> None:
        self._attempts: dict[str, AttemptRecord] = {}
        self._recordings: dict[str, RecordingRecord] = {}
        self._artifacts: dict[str, list[DerivedArtifactRecord]] = {}
        self._lock = Lock()

    def create_attempt(self, record: AttemptRecord) -> AttemptRecord:
        with self._lock:
            self._attempts[record.attempt_id] = record
            return record

    def get_attempt(self, attempt_id: str) -> AttemptRecord | None:
        with self._lock:
            return self._attempts.get(attempt_id)

    def save_attempt(self, record: AttemptRecord) -> AttemptRecord:
        with self._lock:
            self._attempts[record.attempt_id] = record
            return record

    def attach_recording(self, record: RecordingRecord) -> RecordingRecord:
        with self._lock:
            if record.attempt_id not in self._attempts:
                raise AttemptNotFoundError(record.attempt_id)
            self._recordings[record.recording_id] = record
            return record

    def get_recording(self, recording_id: str) -> RecordingRecord | None:
        with self._lock:
            return self._recordings.get(recording_id)

    def save_artifact(self, artifact: DerivedArtifactRecord) -> DerivedArtifactRecord:
        with self._lock:
            self._artifacts.setdefault(artifact.recording_id, []).append(artifact)
            return artifact

    def list_artifacts_for_recording(self, recording_id: str) -> list[DerivedArtifactRecord]:
        with self._lock:
            return list(self._artifacts.get(recording_id, []))


REPOSITORY = InMemoryCommunicationRepository()
