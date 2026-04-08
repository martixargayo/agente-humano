from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict


class BoundConversationSimpleContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flow_id: str
    context_id: str
    context_version: str


class ResolvedConversationSimpleContext(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    flow_id: str
    context_id: str
    context_version: str
    public_slug: str
    context_dir: Path
    presentation_dir: Path
    prompts_dir: Path
    persona_path: Path
    conversation_brief_path: Path
    phase_cards_path: Path
    resolution_source: str
