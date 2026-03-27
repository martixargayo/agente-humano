from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from comunicacion.storage.models import AttemptStatus
from evaluacion.contracts.communication_models import CommunicationEvaluationStatusResponse, UiCommunicationReportV1


class CommunicationPresentationConfig(BaseModel):
    model_config = ConfigDict(extra='allow')

    version: str
    theme: str


class CommunicationActivityBrief(BaseModel):
    model_config = ConfigDict(extra='allow')

    title: str
    description: str | None = None


class CommunicationCapturePolicy(BaseModel):
    model_config = ConfigDict(extra='allow')

    min_duration_ms: int
    max_duration_ms: int
    allow_rerecord: bool = True
    audio_required: bool = True
    video_required: bool = True
    accepted_mime_types: list[str] = Field(default_factory=list)


class CommunicationSessionBootstrapRequest(BaseModel):
    user_id: str | None = None
    session_id: str | None = None
    context_id: str | None = None
    public_slug: str | None = None


class CommunicationSessionBootstrapResponse(BaseModel):
    user_id: str
    session_id: str
    session_bootstrap_state: Literal['new', 'rehydrated']
    existing_session: bool = False
    context_id: str
    public_slug: str
    presentation_config: CommunicationPresentationConfig
    activity_brief: CommunicationActivityBrief
    capture_policy: CommunicationCapturePolicy
    trace_count: int = 0
    last_updated: str
    communication_status: str = 'bootstrap_ready'
    last_attempt_id: str | None = None
    last_evaluation_id: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class CreateAttemptRequest(BaseModel):
    user_id: str
    session_id: str


class CreateAttemptResponse(BaseModel):
    attempt_id: str
    status: AttemptStatus
    context_id: str
    recording_id: str | None = None
    latest_evaluation_id: str | None = None
    rerecord_count: int = 0


class GetAttemptResponse(BaseModel):
    attempt_id: str
    status: AttemptStatus
    context_id: str
    recording_id: str | None = None
    latest_evaluation_id: str | None = None
    rerecord_count: int = 0
    created_at: datetime
    updated_at: datetime


class UploadRecordingRequest(BaseModel):
    user_id: str
    session_id: str
    mime_type: str
    duration_ms: int
    video_ref: str
    video_blob_base64: str | None = None
    poster_frame_ref: str | None = None
    capture_meta: dict[str, Any] = Field(default_factory=dict)


class UploadRecordingResponse(BaseModel):
    attempt_id: str
    recording_id: str
    status: AttemptStatus
    video_ref: str
    playback_url: str | None = None
    poster_frame_ref: str | None = None


class SubmitAttemptRequest(BaseModel):
    user_id: str
    session_id: str


class SubmitAttemptResponse(BaseModel):
    attempt_id: str
    evaluation_id: str
    status: Literal['queued', 'running', 'completed', 'failed']


class CommunicationEvaluationReportResponse(UiCommunicationReportV1):
    pass


class CommunicationEvaluationStatusApiResponse(CommunicationEvaluationStatusResponse):
    pass
