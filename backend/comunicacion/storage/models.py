from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AttemptStatus = Literal['draft', 'uploaded', 'submitted', 'completed', 'failed']
ArtifactKind = Literal['poster_frame', 'transcript', 'audio_features', 'visual_summary', 'bundle_snapshot']


class AttemptRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    attempt_id: str
    user_id: str
    session_id: str
    flow_id: Literal['comunicacion'] = 'comunicacion'
    context_id: str
    status: AttemptStatus = 'draft'
    recording_id: str | None = None
    latest_evaluation_id: str | None = None
    rerecord_count: int = 0
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None = None


class RecordingRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    recording_id: str
    attempt_id: str
    user_id: str
    session_id: str
    mime_type: str
    duration_ms: int
    video_ref: str
    poster_frame_ref: str | None = None
    capture_meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class DerivedArtifactRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    artifact_id: str
    recording_id: str
    kind: ArtifactKind
    version: str
    storage_ref: str
    content_hash: str | None = None
    created_at: datetime
