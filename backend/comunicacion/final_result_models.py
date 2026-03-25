from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class CommunicationFinalResultMedia(BaseModel):
    model_config = ConfigDict(extra='forbid')

    video_ref: str
    poster_frame_ref: str | None = None
    duration_ms: int
    mime_type: str


class CommunicationFinalResultPayloadV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal['comunicacion_final_result.v1'] = 'comunicacion_final_result.v1'
    activity_type: Literal['comunicacion'] = 'comunicacion'
    title: str
    activityid: str
    session_id: str
    user_id: str
    attempt_id: str
    recording_id: str
    evaluation_id: str
    context_id: str
    public_slug: str
    summary_html: str
    snapshot_png_dataurl: str
    payloadjson: dict[str, Any]
    video_ref: str
    poster_frame_ref: str | None = None
    duration_ms: int
    payload_hash: str
    created_at: str
    media: CommunicationFinalResultMedia


class CommunicationFinalResultEnvelopeV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    ns: Literal['gestionce.simulator'] = 'gestionce.simulator'
    v: Literal[1] = 1
    type: Literal['final_result'] = 'final_result'
    correlation_id: str
    session_id: str | None = None
    context_id: str | None = None
    public_slug: str | None = None
    payload: CommunicationFinalResultPayloadV1


class CommunicationFinalResultSavedAckV1(BaseModel):
    model_config = ConfigDict(extra='forbid')

    ns: Literal['gestionce.simulator'] = 'gestionce.simulator'
    v: Literal[1] = 1
    type: Literal['final_result_saved'] = 'final_result_saved'
    payload: dict[str, Any]
