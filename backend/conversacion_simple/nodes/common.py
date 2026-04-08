from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class DialogueMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    text: str


class UserTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_text: str
    normalized_text: str
    modality: Literal["text"]
    language: str
    timestamp_iso: str


class TraceMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str
    prompt_version: str
    schema_version: str
    model_target: str
